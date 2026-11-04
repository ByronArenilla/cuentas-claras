"""La conversación del bot, sin nada de Telegram (spec 005; principio 10).

`Conversations.handle` recibe un evento de un chat (un comando, un texto o
un botón) y devuelve las respuestas que el bot debe enviar. El adaptador de
`telegram_app.py` solo traduce entre Telegram y estos tipos.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from bot.api import ApiUnavailable, InvalidCode, NotLinked
from bot.parsing import parse_amount

# --- Eventos y respuestas ---


@dataclass(frozen=True)
class Command:
    """Un comando como `/vincular ABCD-EFGH`: `name="vincular"`, `args`."""

    name: str
    args: str = ""


@dataclass(frozen=True)
class Text:
    """Un mensaje de texto que no es un comando."""

    text: str


@dataclass(frozen=True)
class Press:
    """Un botón tocado; `data` es el que se le dio al crearlo."""

    data: str


Event = Command | Text | Press


@dataclass(frozen=True)
class Button:
    label: str
    data: str


@dataclass(frozen=True)
class Reply:
    """Un mensaje del bot, con filas de botones opcionales."""

    text: str
    buttons: tuple[tuple[Button, ...], ...] = ()


class Api(Protocol):
    """Lo que la conversación necesita de `bot.api.ApiClient`."""

    async def is_linked(self, chat_id: int) -> bool: ...
    async def link_chat(self, chat_id: int, code: str) -> str: ...
    async def unlink_chat(self, chat_id: int) -> None: ...
    async def spaces(self, chat_id: int) -> list[dict]: ...
    async def categories(self, chat_id: int, space_id: int) -> list[dict]: ...
    async def create_expense(self, chat_id: int, space_id: int, body: dict) -> dict: ...
    async def summary(self, chat_id: int, space_id: int, period: str) -> dict: ...


def utc_now() -> datetime:
    return datetime.now(UTC)


# --- Mensajes (RF-28: todos en español) ---

HELP = (
    "Hola, soy el bot de gastito: te ayudo a registrar tus gastos.\n\n"
    "/gasto: registrar un gasto. También puedes escribir solo el monto, "
    "por ejemplo 20.000.\n"
    "/cancelar: descartar el gasto que estás registrando.\n"
    "/vincular CÓDIGO: vincular este chat a tu cuenta de gastito.\n"
    "/desvincular: quitar la vinculación de este chat."
)
LINK_HELP = (
    "Este chat no está vinculado a ninguna cuenta de gastito. Pide un código "
    "de vinculación con tu sesión (POST /telegram/link-codes) y envíamelo "
    "así:\n/vincular ABCD-EFGH\nEl código caduca a los 10 minutos."
)
LINK_USAGE = "Envíame el código así: /vincular ABCD-EFGH"
LINK_INVALID = "Ese código no es válido, ya se usó o caducó. Pide uno nuevo."
UNLINKED = (
    "Listo: desvinculé este chat. Para volver a usarlo, vincúlalo con un código nuevo."
)
UNAVAILABLE = "No pude hablar con gastito. Intenta de nuevo en un rato."
ASK_AMOUNT = "¿Cuánto gastaste? Escribe el monto en pesos, por ejemplo 20.000."


class Conversations:
    """Las conversaciones de todos los chats, con su estado en memoria."""

    def __init__(
        self,
        api: Api,
        tz: str,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.api = api
        self.tz = ZoneInfo(tz)
        # Instante actual en UTC; los tests pasan uno fijo (principio 7).
        self.clock = clock

    async def handle(self, chat_id: int, event: Event) -> list[Reply]:
        """Respuestas del bot a un evento del chat."""
        try:
            return await self._dispatch(chat_id, event)
        except NotLinked:
            return [Reply(LINK_HELP)]
        except ApiUnavailable:
            return [Reply(UNAVAILABLE)]

    async def _dispatch(self, chat_id: int, event: Event) -> list[Reply]:
        if isinstance(event, Command):
            return await self._command(chat_id, event)
        if isinstance(event, Text):
            return await self._text(chat_id, event.text)
        return [Reply(HELP)]

    async def _command(self, chat_id: int, command: Command) -> list[Reply]:
        if command.name in ("start", "ayuda"):
            return await self._help(chat_id)
        if command.name == "vincular":
            return await self._link(chat_id, command.args)
        if command.name == "desvincular":
            await self.api.unlink_chat(chat_id)
            return [Reply(UNLINKED)]
        if command.name == "gasto":
            return await self._start_expense(chat_id)
        return [Reply(HELP)]

    async def _text(self, chat_id: int, text: str) -> list[Reply]:
        if parse_amount(text) is not None:
            return await self._start_expense(chat_id)
        return [Reply(HELP)]

    async def _help(self, chat_id: int) -> list[Reply]:
        """Los comandos y, si el chat no está vinculado, cómo vincularlo
        (RF-27). Saber si lo está no toca ninguna ruta de datos (RF-7)."""
        if await self.api.is_linked(chat_id):
            return [Reply(HELP)]
        return [Reply(HELP), Reply(LINK_HELP)]

    async def _link(self, chat_id: int, code: str) -> list[Reply]:
        """`/vincular CÓDIGO` (RF-3, RF-4)."""
        if not code.strip():
            return [Reply(LINK_USAGE)]
        try:
            email = await self.api.link_chat(chat_id, code.strip())
        except InvalidCode:
            return [Reply(LINK_INVALID)]
        return [
            Reply(
                f"Listo: este chat quedó vinculado a {email}. Ya puedes "
                "registrar gastos con /gasto."
            )
        ]

    async def _start_expense(self, chat_id: int) -> list[Reply]:
        """Empieza un gasto. Lo primero es saber los espacios del usuario: si
        el chat no está vinculado, `NotLinked` corta aquí (RF-7)."""
        await self.api.spaces(chat_id)
        return [Reply(ASK_AMOUNT)]
