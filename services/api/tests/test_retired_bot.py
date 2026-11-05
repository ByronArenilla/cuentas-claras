"""El bot de Telegram se retiró (spec 007, ADR 0010).

Estos tests vigilan que no quede ninguna puerta del bot en la API ni sus
tablas en una base nueva.
"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.db import build_engine
from app.models import Base
from tests.old_schemas import TELEGRAM_TABLES

# La llave que usaba el bot. Ya no debe abrir nada.
BOT_KEY = {"X-Bot-Key": "llave-de-prueba-del-bot-32-chars"}

# Las rutas que tenía la 005, con un cuerpo válido para cada una.
TELEGRAM_ROUTES = [
    ("POST", "/telegram/link-codes", None),
    ("POST", "/telegram/chats", {"chat_id": 123, "code": "ABCD-EFGH"}),
    ("DELETE", "/telegram/chats/123", None),
    ("POST", "/telegram/sessions", {"chat_id": 123}),
]

# --- Criterios 1 y 2: ninguna ruta ni llave del bot (RF-1, RF-3) ---


@pytest.mark.parametrize(("method", "path", "body"), TELEGRAM_ROUTES)
@pytest.mark.parametrize("with_key", [False, True])
def test_telegram_routes_no_longer_exist(
    client: TestClient,
    login: Callable[[str], dict[str, str]],
    method: str,
    path: str,
    body: dict | None,
    with_key: bool,
) -> None:
    headers = {**login("ana@example.com"), **(BOT_KEY if with_key else {})}

    response = client.request(method, path, json=body, headers=headers)

    assert response.status_code == 404


def test_bot_key_without_session_is_just_unauthenticated(client: TestClient) -> None:
    with_key = client.get("/spaces", headers=BOT_KEY)
    without = client.get("/spaces")

    assert with_key.status_code == 401
    assert with_key.json() == without.json()


def test_docs_no_longer_mention_telegram(client: TestClient) -> None:
    schema = client.get("/openapi.json").text

    assert "/telegram" not in schema
    assert "X-Bot-Key" not in schema


# --- Criterio 4 de la 007: ya no aplica ---
# Decía que una base vieja conservaba las tablas de Telegram. La 008 las borra
# en su primera migración, como pedía la 007 (decisión 1): lo comprueba
# `test_migrations.py`.


# --- Criterio 5: una base nueva no tiene tablas de Telegram (RF-6) ---


def test_a_new_database_has_no_telegram_tables() -> None:
    engine = build_engine("sqlite://")
    Base.metadata.create_all(engine)

    tables = set(inspect(engine).get_table_names())

    assert tables  # create_all sí creó las tablas de la app
    assert not tables & TELEGRAM_TABLES
    engine.dispose()
