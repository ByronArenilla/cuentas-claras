import os
from collections.abc import Callable, Iterator

import pytest

# La configuración se lee al importar `app`, así que el entorno de pruebas se
# fija antes de cualquier import de la app. Se sobrescribe a propósito: los
# tests nunca deben depender del `.env` local ni tocar una base de datos real.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["TZ"] = "America/Bogota"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import build_engine, create_all, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def engine() -> Iterator[Engine]:
    """Base de datos SQLite en memoria, nueva y vacía para cada test."""
    engine = build_engine("sqlite://")
    create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    """Cliente HTTP de la API conectado a la base de datos en memoria del test."""

    def override_get_db() -> Iterator[Session]:
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


PASSWORD = "una-contraseña-larga"


@pytest.fixture
def login(client: TestClient) -> Callable[[str], dict[str, str]]:
    """Registra un usuario, inicia su sesión y devuelve la cabecera con el token."""

    def _login(email: str = "ana@example.com") -> dict[str, str]:
        client.post("/auth/register", json={"email": email, "password": PASSWORD})
        response = client.post(
            "/auth/login", json={"email": email, "password": PASSWORD}
        )
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login
