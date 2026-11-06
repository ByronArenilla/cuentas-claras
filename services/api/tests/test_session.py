from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.models import Session as SessionRow
from app.models import User
from app.security import hash_token
from tests.conftest import PASSWORD

Login = Callable[..., dict[str, str]]


def register(client: TestClient, email: str = "ana@example.com") -> None:
    client.post("/auth/register", json={"email": email, "password": PASSWORD})


def post_login(client: TestClient, email: str, password: str = PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def session_rows(engine: Engine) -> list[SessionRow]:
    with Session(engine) as db:
        return list(db.scalars(select(SessionRow)))


def count_sessions(engine: Engine) -> int:
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(SessionRow))


# --- Entrar (RF-8, RF-9) ---


def test_login_returns_token_and_stores_only_its_hash(
    client: TestClient, engine: Engine
) -> None:
    register(client)

    response = post_login(client, "ana@example.com")

    assert response.status_code == 200
    token = response.json()["access_token"]
    assert response.json()["token_type"] == "bearer"
    [row] = session_rows(engine)
    assert row.token_hash == hash_token(token)
    assert token not in row.token_hash


def test_session_lasts_ninety_days(client: TestClient, engine: Engine) -> None:
    # Spec 011, RF-5: cambia los 15 días de la 001.
    register(client)

    post_login(client, "ana@example.com")

    [row] = session_rows(engine)
    expected = datetime.now(UTC) + timedelta(days=90)
    assert abs(row.expires_at - expected) < timedelta(minutes=1)


def test_login_ignores_email_case(client: TestClient) -> None:
    register(client)

    assert post_login(client, " ANA@example.com ").status_code == 200


def test_wrong_email_and_wrong_password_look_the_same(
    client: TestClient, engine: Engine
) -> None:
    register(client)

    wrong_password = post_login(client, "ana@example.com", "otra-contraseña-larga")
    wrong_email = post_login(client, "nadie@example.com")

    assert wrong_password.status_code == wrong_email.status_code == 401
    assert wrong_password.json() == wrong_email.json()
    assert count_sessions(engine) == 0


# --- Identificarse (RF-10, RF-11) ---


def test_me_returns_the_logged_in_user(client: TestClient, login: Login) -> None:
    headers = login("ana@example.com")

    response = client.get("/me", headers=headers)

    assert response.status_code == 200
    assert response.json()["email"] == "ana@example.com"
    assert "password" not in response.text


def test_each_token_identifies_its_own_user(client: TestClient, login: Login) -> None:
    ana, bea = login("ana@example.com"), login("bea@example.com")

    assert client.get("/me", headers=ana).json()["email"] == "ana@example.com"
    assert client.get("/me", headers=bea).json()["email"] == "bea@example.com"


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer token-desconocido"},
        {"Authorization": "Basic YW5hOmNsYXZl"},
        {"Authorization": "Bearer"},
    ],
    ids=["sin-token", "token-desconocido", "otro-esquema", "bearer-vacio"],
)
def test_me_without_a_valid_token_is_401(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.get("/me", headers=headers)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_expired_session_is_401_and_is_left_untouched(
    client: TestClient, engine: Engine
) -> None:
    register(client)
    token = "token-caducado"
    with Session(engine) as db:
        user_id = db.scalars(select(User.id)).one()
        db.add(
            SessionRow(
                token_hash=hash_token(token),
                user_id=user_id,
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        db.commit()

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert count_sessions(engine) == 1


# --- Salir (RF-12) ---


def test_token_is_401_after_logout(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # Criterio de validación 3: el token deja de servir aunque no haya caducado.
    headers = login()

    response = client.post("/auth/logout", headers=headers)

    assert response.status_code == 204
    assert count_sessions(engine) == 0
    assert client.get("/me", headers=headers).status_code == 401


def test_logout_only_closes_the_current_session(
    client: TestClient, login: Login
) -> None:
    phone = login("ana@example.com")
    laptop_token = post_login(client, "ana@example.com").json()["access_token"]
    laptop = {"Authorization": f"Bearer {laptop_token}"}

    client.post("/auth/logout", headers=phone)

    assert client.get("/me", headers=phone).status_code == 401
    assert client.get("/me", headers=laptop).status_code == 200


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer token-desconocido"}])
def test_request_without_session_changes_nothing(
    client: TestClient, engine: Engine, login: Login, headers: dict[str, str]
) -> None:
    # Criterio de validación 4: sin sesión válida no se ejecuta la operación.
    login()

    response = client.post("/auth/logout", headers=headers)

    assert response.status_code == 401
    assert count_sessions(engine) == 1


# --- Sesión renovable (spec 011, RF-5) ---


def logged_in(client: TestClient) -> dict[str, str]:
    register(client)
    token = post_login(client, "ana@example.com").json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def set_expiry(engine: Engine, expires_at: datetime) -> None:
    """Mueve la caducidad de la única sesión: así se simula que pasaron días
    sin cambiar el reloj."""
    with Session(engine) as db:
        row = db.scalars(select(SessionRow)).one()
        row.expires_at = expires_at
        db.commit()


def expiry(engine: Engine) -> datetime:
    [row] = session_rows(engine)
    return row.expires_at


def test_using_the_session_renews_it_to_ninety_days(
    client: TestClient, engine: Engine
) -> None:
    # Como si se hubiera entrado hace 10 días.
    headers = logged_in(client)
    set_expiry(engine, datetime.now(UTC) + timedelta(days=80))

    assert client.get("/me", headers=headers).status_code == 200

    expected = datetime.now(UTC) + timedelta(days=90)
    assert abs(expiry(engine) - expected) < timedelta(minutes=1)


def test_the_session_is_renewed_at_most_once_a_day(
    client: TestClient, engine: Engine
) -> None:
    # Renovada hace unas horas: le quedan más de 89 días y no se escribe.
    headers = logged_in(client)
    recent = datetime.now(UTC) + timedelta(days=89, hours=20)
    set_expiry(engine, recent)

    client.get("/me", headers=headers)
    client.get("/spaces", headers=headers)

    assert abs(expiry(engine) - recent) < timedelta(seconds=1)


def test_an_expired_session_is_not_renewed(client: TestClient, engine: Engine) -> None:
    headers = logged_in(client)
    expired = datetime.now(UTC) - timedelta(minutes=1)
    set_expiry(engine, expired)

    assert client.get("/me", headers=headers).status_code == 401
    assert abs(expiry(engine) - expired) < timedelta(seconds=1)


def test_logging_out_ends_a_renewed_session(client: TestClient, engine: Engine) -> None:
    headers = logged_in(client)
    set_expiry(engine, datetime.now(UTC) + timedelta(days=30))
    client.get("/me", headers=headers)

    client.post("/auth/logout", headers=headers)

    assert client.get("/me", headers=headers).status_code == 401
