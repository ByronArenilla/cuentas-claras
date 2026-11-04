"""Cliente de la API de gastito para el bot (spec 005).

El bot solo habla con la API por HTTP (principio 9). Para vincular chats y
pedir sesiones usa la llave del bot; para los datos, la sesión del usuario
del chat, que guarda en memoria y renueva cuando caduca (RF-10, RF-11).
"""

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

# Si la API no responde en este tiempo, se da por no disponible (RF-25).
TIMEOUT_SECONDS = 10.0


class ApiError(Exception):
    """Algo impidió completar una llamada a la API."""


class NotLinked(ApiError):
    """El chat no está vinculado a ningún usuario (RF-7)."""


class InvalidCode(ApiError):
    """El código de vinculación no existe, ya se usó o caducó (RF-4)."""


class ApiRejected(ApiError):
    """La API rechazó la petición; `detail` es su motivo, en español."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class ApiUnavailable(ApiError):
    """La API no respondió, falló o rechazó la configuración del bot."""


def error_detail(response: httpx.Response) -> str:
    """El mensaje de error de la API. Los errores de validación de FastAPI
    traen una lista: se unen sus mensajes en un solo texto."""
    try:
        detail = response.json()["detail"]
    except (ValueError, KeyError, TypeError):
        return response.text or f"Error {response.status_code}"
    if isinstance(detail, list):
        return " ".join(str(item.get("msg", item)) for item in detail)
    return str(detail)


class ApiClient:
    """Llamadas a la API en nombre de cada chat."""

    def __init__(
        self,
        base_url: str,
        bot_api_key: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        # `transport` solo se pasa en los tests, con `httpx.MockTransport`.
        self._http = httpx.AsyncClient(
            base_url=base_url, timeout=TIMEOUT_SECONDS, transport=transport
        )
        self._bot_headers = {"X-Bot-Key": bot_api_key}
        # Token de sesión de cada chat. Vive solo en memoria: al reiniciar el
        # bot se piden sesiones nuevas (decisión 8).
        self._tokens: dict[int, str] = {}

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _send(self, method: str, url: str, **kwargs: Any) -> httpx.Response:  # noqa: ANN401
        """Envía la petición; sin conexión o con un `5xx`, `ApiUnavailable`."""
        try:
            response = await self._http.request(method, url, **kwargs)
        except httpx.TransportError as error:
            raise ApiUnavailable(str(error)) from error
        if response.status_code >= 500:
            raise ApiUnavailable(f"{method} {url}: {response.status_code}")
        return response

    async def _as_bot(self, method: str, url: str, **kwargs: Any) -> httpx.Response:  # noqa: ANN401
        """Petición con la llave del bot. Un `401` es un fallo de
        configuración (la llave no coincide), no algo que el usuario pueda
        resolver: se registra y se trata como API no disponible."""
        response = await self._send(method, url, headers=self._bot_headers, **kwargs)
        if response.status_code == 401:
            log.error("La API rechazó la llave del bot: revisa BOT_API_KEY.")
            raise ApiUnavailable("Llave del bot no válida.")
        return response

    async def _token(self, chat_id: int) -> str:
        """Token de sesión del chat; si no hay, pide uno a la API (RF-10)."""
        if chat_id in self._tokens:
            return self._tokens[chat_id]
        response = await self._as_bot(
            "POST", "/telegram/sessions", json={"chat_id": chat_id}
        )
        if response.status_code == 404:
            raise NotLinked(error_detail(response))
        if response.is_error:
            raise ApiRejected(error_detail(response))
        token = response.json()["access_token"]
        self._tokens[chat_id] = token
        return token

    async def _as_chat(self, chat_id: int, method: str, url: str, **kwargs: Any) -> Any:  # noqa: ANN401
        """Petición en nombre del usuario del chat. Si la sesión caducó
        (`401`), pide otra y repite una sola vez (RF-11)."""
        for attempt in range(2):
            token = await self._token(chat_id)
            response = await self._send(
                method, url, headers={"Authorization": f"Bearer {token}"}, **kwargs
            )
            if response.status_code == 401 and attempt == 0:
                self._tokens.pop(chat_id, None)
                continue
            if response.is_error:
                raise ApiRejected(error_detail(response))
            return response.json() if response.content else None
        raise AssertionError("inalcanzable")  # pragma: no cover

    async def _forget(self, chat_id: int) -> None:
        """Cierra la sesión guardada del chat, si hay una. Si la API no
        responde, basta con olvidarla: caduca sola en una hora (decisión 7)."""
        token = self._tokens.pop(chat_id, None)
        if token is None:
            return
        try:
            await self._send(
                "POST", "/auth/logout", headers={"Authorization": f"Bearer {token}"}
            )
        except ApiUnavailable:
            log.warning("No se pudo cerrar la sesión del chat %s.", chat_id)

    # --- Vinculación (RF-3 a RF-6) ---

    async def link_chat(self, chat_id: int, code: str) -> str:
        """Vincula el chat con el código y devuelve el correo del usuario.

        Antes cierra la sesión que hubiera: si el chat pasa a otro usuario,
        la del anterior no se sigue usando (RF-5).
        """
        await self._forget(chat_id)
        response = await self._as_bot(
            "POST", "/telegram/chats", json={"chat_id": chat_id, "code": code}
        )
        if response.status_code == 400:
            raise InvalidCode(error_detail(response))
        if response.is_error:
            raise ApiRejected(error_detail(response))
        return response.json()["email"]

    async def unlink_chat(self, chat_id: int) -> None:
        """Cierra la sesión del chat y quita la vinculación (RF-6)."""
        await self._forget(chat_id)
        response = await self._as_bot("DELETE", f"/telegram/chats/{chat_id}")
        if response.is_error:
            raise ApiRejected(error_detail(response))

    # --- Datos, en nombre del usuario del chat ---

    async def spaces(self, chat_id: int) -> list[dict]:
        return await self._as_chat(chat_id, "GET", "/spaces")

    async def categories(self, chat_id: int, space_id: int) -> list[dict]:
        return await self._as_chat(chat_id, "GET", f"/spaces/{space_id}/categories")

    async def create_expense(self, chat_id: int, space_id: int, body: dict) -> dict:
        return await self._as_chat(
            chat_id, "POST", f"/spaces/{space_id}/expenses", json=body
        )

    async def summary(self, chat_id: int, space_id: int, period: str) -> dict:
        return await self._as_chat(
            chat_id, "GET", f"/spaces/{space_id}/summary", params={"period": period}
        )
