"""Vinculación de chats de Telegram y sesiones del bot (spec 005)."""

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.models import TelegramLinkCode
from app.security import LINK_CODE_ALPHABET, generate_link_code, normalize_link_code

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
