"""Vinculación de chats de Telegram y sesiones del bot (spec 005)."""

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.models import Session as SessionRow
from app.models import TelegramChat, TelegramLinkCode
from app.routers.telegram import claim_link_code
from app.security import (
    LINK_CODE_ALPHABET,
    generate_link_code,
    hash_token,
    normalize_link_code,
)
from tests.conftest import BOT_API_KEY

Login = Callable[..., dict[str, str]]

CODE_FORMAT = re.compile(r"[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}")


# --- Pedir un código (T3) ---


def test_alphabet_is_crockford_base32() -> None:
    # Sin I, L, O ni U, que se confunden con 1, 0 o V al copiar (plan 005).
    assert len(LINK_CODE_ALPHABET) == 32
    assert not set("ILOU") & set(LINK_CODE_ALPHABET)


def test_generated_code_has_the_expected_shape() -> None:
    codes = {generate_link_code() for _ in range(50)}

    assert all(CODE_FORMAT.fullmatch(code) for code in codes)
    assert len(codes) == 50  # Aleatorios: no se repiten.


@pytest.mark.parametrize(
    "typed", ["ABCD-EFGH", "abcd-efgh", " abcd efgh ", "ABCDEFGH", "ab-cd-ef-gh"]
)
def test_normalize_ignores_case_spaces_and_dashes(typed: str) -> None:
    assert normalize_link_code(typed) == "ABCDEFGH"


def request_code(client: TestClient, headers: dict[str, str]) -> Response:
    return client.post("/telegram/link-codes", headers=headers)


def test_a_user_gets_a_code_that_expires_in_ten_minutes(
    client: TestClient, login: Login
) -> None:
    # RF-1.
    before = datetime.now(UTC)

    response = request_code(client, login("ana@example.com"))

    assert response.status_code == 201
    body = response.json()
    assert CODE_FORMAT.fullmatch(body["code"])
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert before + timedelta(minutes=10) <= expires_at
    assert expires_at <= datetime.now(UTC) + timedelta(minutes=10)


def test_only_the_hash_of_the_code_is_stored(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # RF-2.
    code = request_code(client, login("ana@example.com")).json()["code"]

    with Session(engine) as db:
        stored = db.scalars(select(TelegramLinkCode.code_hash)).one()
    assert normalize_link_code(code) not in stored
    assert code not in stored
    assert len(stored) == 64


def test_requesting_a_code_without_session_is_rejected(
    client: TestClient, engine: Engine
) -> None:
    assert request_code(client, {}).status_code == 401
    with Session(engine) as db:
        assert db.scalars(select(TelegramLinkCode)).all() == []


# --- Vincular, desvincular y sesiones del bot (T4) ---

BOT = {"X-Bot-Key": BOT_API_KEY}
CODE_INVALID = "El código no es válido, ya se usó o caducó."
CHAT = 555_000_111


def link(
    client: TestClient, code: str, chat_id: int = CHAT, headers: dict | None = None
) -> Response:
    return client.post(
        "/telegram/chats",
        json={"chat_id": chat_id, "code": code},
        headers=BOT if headers is None else headers,
    )


def bot_session(
    client: TestClient, chat_id: int = CHAT, headers: dict | None = None
) -> Response:
    return client.post(
        "/telegram/sessions",
        json={"chat_id": chat_id},
        headers=BOT if headers is None else headers,
    )


def linked_user(engine: Engine, chat_id: int = CHAT) -> int | None:
    with Session(engine) as db:
        return db.scalar(
            select(TelegramChat.user_id).where(TelegramChat.chat_id == chat_id)
        )


def user_id(client: TestClient, headers: dict[str, str]) -> int:
    return client.get("/me", headers=headers).json()["id"]


def test_a_valid_code_links_the_chat_and_names_the_user(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # Criterio 1 (RF-3).
    ana = login("ana@example.com")
    code = request_code(client, ana).json()["code"]

    response = link(client, code.lower())  # Se ignoran mayúsculas.

    assert response.status_code == 200
    assert response.json() == {"email": "ana@example.com"}
    assert linked_user(engine) == user_id(client, ana)


def test_a_code_works_only_once(client: TestClient, login: Login) -> None:
    # Criterio 1 (RF-4).
    code = request_code(client, login("ana@example.com")).json()["code"]
    link(client, code)

    response = link(client, code, chat_id=CHAT + 1)

    assert response.status_code == 400
    assert response.json()["detail"] == CODE_INVALID


def test_an_unknown_code_is_rejected_with_the_same_message(
    client: TestClient, engine: Engine
) -> None:
    response = link(client, "ABCD-EFGH")

    assert response.status_code == 400
    assert response.json()["detail"] == CODE_INVALID
    assert linked_user(engine) is None


def test_an_expired_code_is_rejected_with_the_same_message(
    client: TestClient, engine: Engine, login: Login
) -> None:
    code = request_code(client, login("ana@example.com")).json()["code"]
    with Session(engine) as db:
        row = db.scalars(select(TelegramLinkCode)).one()
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

    response = link(client, code)

    assert response.status_code == 400
    assert response.json()["detail"] == CODE_INVALID
    assert linked_user(engine) is None


def test_claiming_a_code_twice_only_works_once(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # RF-4: el `WHERE used_at IS NULL` hace que de dos usos simultáneos solo
    # uno marque el código.
    code = request_code(client, login("ana@example.com")).json()["code"]
    with Session(engine) as db:
        row = db.scalar(
            select(TelegramLinkCode).where(
                TelegramLinkCode.code_hash == hash_token(normalize_link_code(code))
            )
        )
        assert claim_link_code(db, row) is True
        assert claim_link_code(db, row) is False


def test_linking_a_chat_again_moves_it_to_the_new_user(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # RF-5: un chat nunca es de dos usuarios.
    ana, bea = login("ana@example.com"), login("bea@example.com")
    link(client, request_code(client, ana).json()["code"])

    response = link(client, request_code(client, bea).json()["code"])

    assert response.json() == {"email": "bea@example.com"}
    assert linked_user(engine) == user_id(client, bea)
    with Session(engine) as db:
        assert len(db.scalars(select(TelegramChat)).all()) == 1


@pytest.mark.parametrize("headers", [{}, {"X-Bot-Key": "otra-llave-" + "x" * 32}])
def test_bot_routes_require_the_bot_key(
    client: TestClient, engine: Engine, login: Login, headers: dict[str, str]
) -> None:
    # Criterio 2 (RF-9): ni vincular, ni desvincular, ni pedir sesión.
    ana = login("ana@example.com")
    code = request_code(client, ana).json()["code"]
    link(client, request_code(client, ana).json()["code"])  # Chat ya vinculado.

    responses = {
        "vincular": link(client, code, chat_id=CHAT + 1, headers=headers),
        "desvincular": client.delete(f"/telegram/chats/{CHAT}", headers=headers),
        "sesión": bot_session(client, headers=headers),
    }

    for operation, response in responses.items():
        assert response.status_code == 401, operation
        assert response.json()["detail"] == "Llave del bot no válida.", operation
    assert linked_user(engine) == user_id(client, ana)
    assert linked_user(engine, CHAT + 1) is None
    # El código sigue sin usar: sirve para una petición con la llave buena.
    assert link(client, code, chat_id=CHAT + 1).status_code == 200


def test_a_session_for_a_wrong_key_does_not_reveal_if_the_chat_is_linked(
    client: TestClient,
) -> None:
    # RF-9: el mismo 401 exista o no el chat.
    wrong = {"X-Bot-Key": "x" * 40}
    assert bot_session(client, headers=wrong).status_code == 401
    assert bot_session(client, chat_id=1, headers=wrong).status_code == 401


def test_the_bot_session_acts_as_the_user_and_lasts_one_hour(
    client: TestClient, login: Login
) -> None:
    # Criterio 3 (RF-10, decisión 7).
    ana = login("ana@example.com")
    link(client, request_code(client, ana).json()["code"])
    before = datetime.now(UTC)

    response = bot_session(client)

    assert response.status_code == 201
    body = response.json()
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert before + timedelta(hours=1) <= expires_at
    assert expires_at <= datetime.now(UTC) + timedelta(hours=1)
    as_bot = {"Authorization": f"Bearer {body['access_token']}"}
    assert (
        client.get("/spaces", headers=as_bot).json()
        == client.get("/spaces", headers=ana).json()
    )


def test_an_unlinked_chat_gets_no_session(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # Criterio 3 (RF-6, RF-10).
    link(client, request_code(client, login("ana@example.com")).json()["code"])

    unlinked = client.delete(f"/telegram/chats/{CHAT}", headers=BOT)
    response = bot_session(client)

    assert unlinked.status_code == 204
    assert linked_user(engine) is None
    assert response.status_code == 404
    assert response.json()["detail"] == "Este chat no está vinculado."


def test_unlinking_a_chat_that_was_not_linked_is_fine(client: TestClient) -> None:
    assert client.delete(f"/telegram/chats/{CHAT}", headers=BOT).status_code == 204


def test_unlinking_only_touches_that_chat(
    client: TestClient, engine: Engine, login: Login
) -> None:
    ana = login("ana@example.com")
    link(client, request_code(client, ana).json()["code"])
    link(client, request_code(client, ana).json()["code"], chat_id=CHAT + 1)

    client.delete(f"/telegram/chats/{CHAT}", headers=BOT)

    assert linked_user(engine) is None
    assert linked_user(engine, CHAT + 1) == user_id(client, ana)


def test_login_sessions_still_last_fifteen_days(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # `create_session` se comparte con el bot: el inicio de sesión no cambia.
    login("ana@example.com")
    with Session(engine) as db:
        session = db.scalars(select(SessionRow)).one()
    remaining = session.expires_at - datetime.now(UTC)
    assert timedelta(days=14, hours=23) < remaining <= timedelta(days=15)


@pytest.mark.parametrize(
    "body", [{"chat_id": "123", "code": "ABCD-EFGH"}, {"chat_id": 123}, {}]
)
def test_invalid_link_body_is_rejected(client: TestClient, body: dict) -> None:
    response = client.post("/telegram/chats", json=body, headers=BOT)

    assert response.status_code == 422
