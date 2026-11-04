"""Cliente de la API del bot, contra una API simulada con `MockTransport`."""

import asyncio
import json
from collections.abc import Callable

import httpx
import pytest

from bot.api import (
    ApiClient,
    ApiRejected,
    ApiUnavailable,
    InvalidCode,
    NotFound,
    NotLinked,
)

KEY = "k" * 32
CHAT = 42

Handler = Callable[[httpx.Request], httpx.Response]


class FakeApi:
    """Responde según la ruta y guarda cada petición recibida."""

    def __init__(self, routes: dict[tuple[str, str], Handler | list[Handler]]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        handler = self.routes[(request.method, request.url.path)]
        if isinstance(handler, list):
            handler = handler.pop(0)
        return handler(request)

    def paths(self) -> list[str]:
        return [f"{r.method} {r.url.path}" for r in self.requests]


def reply(status: int, body: object = None) -> Handler:
    return lambda _request: httpx.Response(status, json=body)


def session_reply(token: str = "t1") -> Handler:
    return reply(201, {"access_token": token, "token_type": "bearer"})


def client_for(fake: FakeApi) -> ApiClient:
    return ApiClient("http://api.test", KEY, transport=httpx.MockTransport(fake))


def run(coroutine):  # noqa: ANN001, ANN201
    return asyncio.run(coroutine)


def test_the_first_call_asks_for_a_session_with_the_bot_key() -> None:
    # RF-10.
    fake = FakeApi(
        {
            ("POST", "/telegram/sessions"): session_reply("t1"),
            ("GET", "/spaces"): reply(200, [{"id": 1, "name": "Personal"}]),
        }
    )

    spaces = run(client_for(fake).spaces(CHAT))

    assert spaces == [{"id": 1, "name": "Personal"}]
    session_request, spaces_request = fake.requests
    assert session_request.headers["X-Bot-Key"] == KEY
    assert json.loads(session_request.content) == {"chat_id": CHAT}
    assert spaces_request.headers["Authorization"] == "Bearer t1"
    # La llave del bot nunca viaja en las rutas de datos.
    assert "X-Bot-Key" not in spaces_request.headers


def test_the_token_of_a_chat_is_reused() -> None:
    fake = FakeApi(
        {
            ("POST", "/telegram/sessions"): session_reply(),
            ("GET", "/spaces"): reply(200, []),
        }
    )
    api = client_for(fake)

    async def twice() -> None:
        await api.spaces(CHAT)
        await api.spaces(CHAT)

    run(twice())

    assert fake.paths() == ["POST /telegram/sessions", "GET /spaces", "GET /spaces"]


def test_an_expired_session_is_renewed_and_retried_once() -> None:
    # RF-11.
    fake = FakeApi(
        {
            ("POST", "/telegram/sessions"): [
                session_reply("viejo"),
                session_reply("nuevo"),
            ],
            ("GET", "/spaces"): [reply(401, {"detail": "caducada"}), reply(200, [])],
        }
    )

    assert run(client_for(fake).spaces(CHAT)) == []
    assert fake.paths() == [
        "POST /telegram/sessions",
        "GET /spaces",
        "POST /telegram/sessions",
        "GET /spaces",
    ]
    assert fake.requests[-1].headers["Authorization"] == "Bearer nuevo"


def test_a_second_401_is_not_retried_again() -> None:
    fake = FakeApi(
        {
            ("POST", "/telegram/sessions"): [session_reply(), session_reply()],
            ("GET", "/spaces"): [
                reply(401, {"detail": "no"}),
                reply(401, {"detail": "no"}),
            ],
        }
    )

    with pytest.raises(ApiRejected):
        run(client_for(fake).spaces(CHAT))
    assert len(fake.requests) == 4


def test_an_unlinked_chat_is_not_linked() -> None:
    # RF-7: sin sesión no hay ninguna llamada de datos.
    fake = FakeApi(
        {("POST", "/telegram/sessions"): reply(404, {"detail": "no vinculado"})}
    )

    with pytest.raises(NotLinked):
        run(client_for(fake).spaces(CHAT))
    assert fake.paths() == ["POST /telegram/sessions"]


def test_linking_returns_the_email() -> None:
    fake = FakeApi({("POST", "/telegram/chats"): reply(200, {"email": "ana@x.co"})})

    assert run(client_for(fake).link_chat(CHAT, "ABCD-EFGH")) == "ana@x.co"
    request = fake.requests[0]
    assert request.headers["X-Bot-Key"] == KEY
    assert json.loads(request.content) == {"chat_id": CHAT, "code": "ABCD-EFGH"}


def test_a_rejected_code_is_an_invalid_code() -> None:
    fake = FakeApi({("POST", "/telegram/chats"): reply(400, {"detail": "no válido"})})

    with pytest.raises(InvalidCode):
        run(client_for(fake).link_chat(CHAT, "ABCD-EFGH"))


def test_other_client_errors_carry_the_api_message() -> None:
    # RF-25: el bot puede mostrar el motivo que da la API.
    fake = FakeApi(
        {
            ("POST", "/telegram/sessions"): session_reply(),
            ("POST", "/spaces/1/expenses"): reply(
                422, {"detail": "La categoría no existe en este espacio."}
            ),
        }
    )

    with pytest.raises(ApiRejected) as error:
        run(client_for(fake).create_expense(CHAT, 1, {"amount": 1}))
    assert error.value.detail == "La categoría no existe en este espacio."


def test_validation_errors_are_joined_into_one_message() -> None:
    fake = FakeApi(
        {
            ("POST", "/telegram/sessions"): session_reply(),
            ("POST", "/spaces/1/expenses"): reply(
                422, {"detail": [{"msg": "Uno."}, {"msg": "Dos."}]}
            ),
        }
    )

    with pytest.raises(ApiRejected) as error:
        run(client_for(fake).create_expense(CHAT, 1, {}))
    assert error.value.detail == "Uno. Dos."


@pytest.mark.parametrize(
    "handler",
    [
        reply(500, {"detail": "boom"}),
        reply(503),
    ],
)
def test_server_errors_mean_unavailable(handler: Handler) -> None:
    fake = FakeApi({("POST", "/telegram/sessions"): handler})

    with pytest.raises(ApiUnavailable):
        run(client_for(fake).spaces(CHAT))


def test_no_connection_means_unavailable() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin conexión", request=request)

    api = ApiClient("http://api.test", KEY, transport=httpx.MockTransport(refuse))

    with pytest.raises(ApiUnavailable):
        run(api.spaces(CHAT))


def test_a_wrong_bot_key_means_unavailable_not_a_user_error() -> None:
    # Es un fallo de configuración: el usuario no puede hacer nada.
    fake = FakeApi(
        {
            ("POST", "/telegram/sessions"): reply(
                401, {"detail": "Llave del bot no válida."}
            )
        }
    )

    with pytest.raises(ApiUnavailable):
        run(client_for(fake).spaces(CHAT))


def test_unlinking_closes_the_cached_session_first() -> None:
    # RF-6: la sesión que el bot tenía deja de servir desde ya.
    fake = FakeApi(
        {
            ("POST", "/telegram/sessions"): [session_reply("t1"), session_reply("t2")],
            ("GET", "/spaces"): reply(200, []),
            ("POST", "/auth/logout"): reply(204),
            ("DELETE", f"/telegram/chats/{CHAT}"): reply(204),
        }
    )
    api = client_for(fake)

    async def flow() -> None:
        await api.spaces(CHAT)
        await api.unlink_chat(CHAT)
        await api.spaces(CHAT)  # Sin token guardado: pide otra sesión.

    run(flow())

    assert fake.paths() == [
        "POST /telegram/sessions",
        "GET /spaces",
        "POST /auth/logout",
        f"DELETE /telegram/chats/{CHAT}",
        "POST /telegram/sessions",
        "GET /spaces",
    ]
    assert fake.requests[2].headers["Authorization"] == "Bearer t1"


def test_linking_drops_the_session_of_the_previous_user() -> None:
    # RF-5: si el chat pasa a otro usuario, no se sigue usando la sesión vieja.
    fake = FakeApi(
        {
            ("POST", "/telegram/sessions"): [
                session_reply("ana"),
                session_reply("bea"),
            ],
            ("GET", "/spaces"): reply(200, []),
            ("POST", "/auth/logout"): reply(204),
            ("POST", "/telegram/chats"): reply(200, {"email": "bea@x.co"}),
        }
    )
    api = client_for(fake)

    async def flow() -> None:
        await api.spaces(CHAT)
        await api.link_chat(CHAT, "ABCD-EFGH")
        await api.spaces(CHAT)

    run(flow())

    assert fake.requests[-1].headers["Authorization"] == "Bearer bea"


def test_data_routes_use_the_space_and_period() -> None:
    fake = FakeApi(
        {
            ("POST", "/telegram/sessions"): session_reply(),
            ("GET", "/spaces/7/categories"): reply(200, [{"id": 1, "name": "Hogar"}]),
            ("POST", "/spaces/7/expenses"): reply(201, {"id": 9}),
            ("GET", "/spaces/7/summary"): reply(200, {"period": "2026-10"}),
        }
    )
    api = client_for(fake)

    async def flow() -> tuple:
        return (
            await api.categories(CHAT, 7),
            await api.create_expense(CHAT, 7, {"amount": 20_000}),
            await api.summary(CHAT, 7, "2026-10"),
        )

    categories, expense, summary = run(flow())

    assert categories == [{"id": 1, "name": "Hogar"}]
    assert expense == {"id": 9}
    assert summary == {"period": "2026-10"}
    assert json.loads(fake.requests[2].content) == {"amount": 20_000}
    assert fake.requests[3].url.params["period"] == "2026-10"


@pytest.mark.parametrize(("status", "linked"), [(201, True), (404, False)])
def test_is_linked_only_asks_for_a_session(status: int, linked: bool) -> None:
    # RF-7: saber si el chat está vinculado no toca ninguna ruta de datos.
    fake = FakeApi(
        {
            ("POST", "/telegram/sessions"): session_reply()
            if status == 201
            else reply(404, {"detail": "no"})
        }
    )

    assert run(client_for(fake).is_linked(CHAT)) is linked
    assert fake.paths() == ["POST /telegram/sessions"]


# --- Rutas de la 006 (T2) ---


def test_recent_expenses_sends_limit_and_mine() -> None:
    fake = FakeApi(
        {
            ("POST", "/telegram/sessions"): session_reply(),
            ("GET", "/spaces/3/expenses/recent"): reply(200, [{"id": 9}]),
        }
    )

    expenses = run(client_for(fake).recent_expenses(CHAT, 3, limit=1, mine=True))

    assert expenses == [{"id": 9}]
    params = fake.requests[-1].url.params
    assert (params["limit"], params["mine"]) == ("1", "true")


def test_recent_expenses_defaults_to_five_of_anyone() -> None:
    fake = FakeApi(
        {
            ("POST", "/telegram/sessions"): session_reply(),
            ("GET", "/spaces/3/expenses/recent"): reply(200, []),
        }
    )

    run(client_for(fake).recent_expenses(CHAT, 3))

    params = fake.requests[-1].url.params
    assert (params["limit"], params["mine"]) == ("5", "false")


def test_delete_expense_confirms_explicitly() -> None:
    # Principio 8: el borrado solo sale con `confirm=true`.
    fake = FakeApi(
        {
            ("POST", "/telegram/sessions"): session_reply(),
            ("DELETE", "/spaces/3/expenses/9"): reply(204),
        }
    )

    run(client_for(fake).delete_expense(CHAT, 3, 9))

    assert fake.requests[-1].url.params["confirm"] == "true"


def test_a_missing_expense_is_not_found() -> None:
    # RF-15 de la 006: "ese gasto ya no existe".
    fake = FakeApi(
        {
            ("POST", "/telegram/sessions"): session_reply(),
            ("DELETE", "/spaces/3/expenses/9"): reply(
                404, {"detail": "Gasto no encontrado."}
            ),
        }
    )

    with pytest.raises(NotFound) as error:
        run(client_for(fake).delete_expense(CHAT, 3, 9))
    # Sigue siendo un rechazo de la API, con su mensaje.
    assert isinstance(error.value, ApiRejected)
    assert error.value.detail == "Gasto no encontrado."


def test_me_returns_the_user_of_the_chat() -> None:
    fake = FakeApi(
        {
            ("POST", "/telegram/sessions"): session_reply(),
            ("GET", "/me"): reply(200, {"id": 1, "email": "ana@x.co"}),
        }
    )

    assert run(client_for(fake).me(CHAT)) == {"id": 1, "email": "ana@x.co"}
