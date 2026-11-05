"""El bot de Telegram se retiró (spec 007, ADR 0010).

Estos tests vigilan que no quede ninguna puerta del bot en la API y que una
base de datos creada antes del retiro siga funcionando sin perder nada.
"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, inspect, text

from app.db import build_engine, create_all

# La llave que usaba el bot. Ya no debe abrir nada.
BOT_KEY = {"X-Bot-Key": "llave-de-prueba-del-bot-32-chars"}

# Las rutas que tenía la 005, con un cuerpo válido para cada una.
TELEGRAM_ROUTES = [
    ("POST", "/telegram/link-codes", None),
    ("POST", "/telegram/chats", {"chat_id": 123, "code": "ABCD-EFGH"}),
    ("DELETE", "/telegram/chats/123", None),
    ("POST", "/telegram/sessions", {"chat_id": 123}),
]

# Las tablas tal como las dejó la 005 en SQLite. Se escriben a mano porque los
# modelos ya no existen: así el test reproduce una base vieja de verdad.
OLD_TELEGRAM_TABLES = [
    """CREATE TABLE telegram_link_codes (
        id INTEGER NOT NULL,
        code_hash VARCHAR(64) NOT NULL,
        user_id INTEGER NOT NULL,
        expires_at DATETIME NOT NULL,
        used_at DATETIME,
        created_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (code_hash),
        FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
    )""",
    """CREATE TABLE telegram_chats (
        id INTEGER NOT NULL,
        chat_id BIGINT NOT NULL,
        user_id INTEGER NOT NULL,
        created_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (chat_id),
        FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
    )""",
]
TELEGRAM_TABLES = {"telegram_link_codes", "telegram_chats"}


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


# --- Criterio 4: una base vieja sigue funcionando y no pierde nada (RF-5) ---


def count_rows(engine: Engine) -> dict[str, int]:
    with engine.connect() as connection:
        return {
            table: connection.scalar(text(f"SELECT COUNT(*) FROM {table}"))
            for table in sorted(TELEGRAM_TABLES)
        }


def test_a_database_from_before_keeps_working_and_keeps_its_rows(
    engine: Engine,
    client: TestClient,
    login: Callable[[str], dict[str, str]],
) -> None:
    # Una base de la 005: un usuario con su chat vinculado y un código usado.
    ana = login("ana@example.com")
    with engine.begin() as connection:
        for statement in OLD_TELEGRAM_TABLES:
            connection.execute(text(statement))
        connection.execute(
            text(
                "INSERT INTO telegram_link_codes"
                " (code_hash, user_id, expires_at, used_at, created_at)"
                " VALUES ('h', 1, '2026-11-04 10:10:00', '2026-11-04 10:01:00',"
                " '2026-11-04 10:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO telegram_chats (chat_id, user_id, created_at)"
                " VALUES (4503599627370495, 1, '2026-11-04 10:01:00')"
            )
        )

    # Lo que hace la API al arrancar sobre esa base (ADR 0004).
    create_all(engine)

    space_id = client.get("/spaces", headers=ana).json()[0]["id"]
    categories = client.get(f"/spaces/{space_id}/categories", headers=ana).json()
    category_id = categories[0]["id"]
    created = client.post(
        f"/spaces/{space_id}/expenses",
        json={"amount": 20000, "payment_type": "debit", "category_id": category_id},
        headers=ana,
    )
    summary = client.get(f"/spaces/{space_id}/summary", headers=ana)

    assert created.status_code == 201
    assert summary.status_code == 200
    assert summary.json()["total"]["spent"] == 20000
    assert TELEGRAM_TABLES <= set(inspect(engine).get_table_names())
    assert count_rows(engine) == {"telegram_chats": 1, "telegram_link_codes": 1}


# --- Criterio 5: una base nueva no tiene tablas de Telegram (RF-6) ---


def test_a_new_database_has_no_telegram_tables() -> None:
    engine = build_engine("sqlite://")
    create_all(engine)

    tables = set(inspect(engine).get_table_names())

    assert tables  # create_all sí creó las tablas de la app
    assert not tables & TELEGRAM_TABLES
    engine.dispose()
