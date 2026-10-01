from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.models import Category, Membership, Space, User
from app.routers import auth
from tests.conftest import PASSWORD, token_from

Login = Callable[..., dict[str, str]]
SharedSpace = tuple[int, dict[str, str], dict[str, str]]

# Spec 002, decisión 1.
DEFAULTS = ["Hogar", "Comida", "Transporte", "Salud", "Servicios", "Ocio", "Otros"]


def stored_categories(engine: Engine, space_id: int) -> list[Category]:
    """Categorías del espacio leídas de la base de datos, en orden de creación."""
    with Session(engine) as db:
        return list(
            db.scalars(
                select(Category)
                .where(Category.space_id == space_id)
                .order_by(Category.id)
            )
        )


def count(engine: Engine, model: type) -> int:
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(model))


# --- Predefinidas (RF-1 a RF-3) ---


def test_registering_creates_the_defaults_in_the_personal_space(
    client: TestClient, engine: Engine
) -> None:
    body = {"email": "ana@example.com", "password": PASSWORD}
    space_id = client.post("/auth/register", json=body).json()["personal_space"]["id"]

    names = [category.name for category in stored_categories(engine, space_id)]
    assert names == DEFAULTS


def test_creating_a_space_gives_it_its_own_defaults(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # RF-2: cada espacio tiene sus propias filas, no comparte las de otro.
    ana = login("ana@example.com")
    personal_id = client.get("/spaces", headers=ana).json()[0]["id"]
    casa_id = client.post("/spaces", json={"name": "Casa"}, headers=ana).json()["id"]

    personal = stored_categories(engine, personal_id)
    casa = stored_categories(engine, casa_id)

    assert [category.name for category in casa] == DEFAULTS
    assert not {c.id for c in personal} & {c.id for c in casa}


def test_joining_a_space_does_not_touch_its_categories(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # RF-3: unirse no crea ni duplica categorías.
    ana, bea = login("ana@example.com"), login("bea@example.com")
    casa_id = client.post("/spaces", json={"name": "Casa"}, headers=ana).json()["id"]
    before = [category.id for category in stored_categories(engine, casa_id)]

    url = client.post(f"/spaces/{casa_id}/invitations", headers=ana).json()["url"]
    client.post(f"/invitations/{token_from(url)}/redeem", headers=bea)

    assert [category.id for category in stored_categories(engine, casa_id)] == before


def test_rejected_registration_leaves_no_categories(
    client: TestClient, engine: Engine, login: Login
) -> None:
    login("ana@example.com")
    before = count(engine, Category)

    body = {"email": "ana@example.com", "password": PASSWORD}
    assert client.post("/auth/register", json=body).status_code == 409

    assert count(engine, Category) == before


def test_registration_is_all_or_nothing_with_the_defaults(
    client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # RF-1: si las categorías no se pueden crear, tampoco se crean el usuario,
    # el espacio ni la membresía.
    def broken(*_args: object) -> None:
        raise RuntimeError("fallo simulado")

    monkeypatch.setattr(auth, "add_default_categories", broken)
    body = {"email": "ana@example.com", "password": PASSWORD}

    with pytest.raises(RuntimeError):
        client.post("/auth/register", json=body)

    for model in (User, Space, Membership, Category):
        assert count(engine, model) == 0, model.__name__


# --- Listar (RF-4) ---


def test_a_member_lists_the_categories_in_creation_order(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # Criterio de validación 1.
    ana = login("ana@example.com")
    space_id = client.get("/spaces", headers=ana).json()[0]["id"]

    response = client.get(f"/spaces/{space_id}/categories", headers=ana)

    assert response.status_code == 200
    stored = stored_categories(engine, space_id)
    assert response.json() == [{"id": c.id, "name": c.name} for c in stored]
    assert [category["name"] for category in response.json()] == DEFAULTS
    assert "name_key" not in response.text


def test_two_members_see_the_same_categories(
    client: TestClient, shared_space: SharedSpace
) -> None:
    # Parte del criterio de validación 4.
    space_id, ana, bea = shared_space

    ana_view = client.get(f"/spaces/{space_id}/categories", headers=ana)
    bea_view = client.get(f"/spaces/{space_id}/categories", headers=bea)

    assert ana_view.status_code == bea_view.status_code == 200
    assert ana_view.json() == bea_view.json()


def test_listing_categories_without_a_session_is_rejected(
    client: TestClient, login: Login
) -> None:
    # RF-10 (RF-11 de la 001).
    ana = login("ana@example.com")
    space_id = client.get("/spaces", headers=ana).json()[0]["id"]

    assert client.get(f"/spaces/{space_id}/categories").status_code == 401
