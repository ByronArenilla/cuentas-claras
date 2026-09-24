from collections.abc import Callable

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.deps import member_space
from app.models import Membership, Space, User

Login = Callable[..., dict[str, str]]


def create_space(client: TestClient, headers: dict[str, str], name: str) -> dict:
    response = client.post("/spaces", json={"name": name}, headers=headers)
    assert response.status_code == 201
    return response.json()


def names(client: TestClient, headers: dict[str, str]) -> list[str]:
    return [space["name"] for space in client.get("/spaces", headers=headers).json()]


# --- Crear (RF-13) ---


def test_creating_a_space_leaves_the_creator_as_member(
    client: TestClient, engine: Engine, login: Login
) -> None:
    ana = login("ana@example.com")
    ana_id = client.get("/me", headers=ana).json()["id"]

    space = create_space(client, ana, "Casa")

    assert space["name"] == "Casa"
    with Session(engine) as db:
        members = db.scalars(
            select(Membership.user_id).where(Membership.space_id == space["id"])
        ).all()
    assert members == [ana_id]


def test_space_name_is_trimmed(client: TestClient, login: Login) -> None:
    space = create_space(client, login(), "  Casa  ")

    assert space["name"] == "Casa"


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
def test_invalid_space_name_is_rejected(
    client: TestClient, engine: Engine, login: Login, name: str
) -> None:
    ana = login()

    response = client.post("/spaces", json={"name": name}, headers=ana)

    assert response.status_code == 422
    assert "nombre" in response.text
    assert names(client, ana) == ["Personal"]


def test_creating_a_space_requires_a_session(client: TestClient) -> None:
    assert client.post("/spaces", json={"name": "Casa"}).status_code == 401


# --- Listar (RF-14) ---


def test_list_returns_only_own_spaces(client: TestClient, login: Login) -> None:
    ana, bea = login("ana@example.com"), login("bea@example.com")
    create_space(client, ana, "Casa")
    create_space(client, bea, "Viajes")

    assert names(client, ana) == ["Personal", "Casa"]
    assert names(client, bea) == ["Personal", "Viajes"]


def test_listing_spaces_requires_a_session(client: TestClient) -> None:
    assert client.get("/spaces").status_code == 401


# --- member_space (RF-29, RF-30) ---


def user_named(db: Session, email: str) -> User:
    return db.scalars(select(User).where(User.email == email)).one()


def test_member_space_returns_the_space_to_a_member(
    client: TestClient, engine: Engine, login: Login
) -> None:
    space_id = create_space(client, login("ana@example.com"), "Casa")["id"]

    with Session(engine) as db:
        space = member_space(space_id, user_named(db, "ana@example.com"), db)

    assert (space.id, space.name) == (space_id, "Casa")


def test_foreign_and_missing_spaces_look_the_same(
    client: TestClient, engine: Engine, login: Login
) -> None:
    ana = login("ana@example.com")
    login("bea@example.com")
    foreign_id = create_space(client, ana, "Casa")["id"]

    with Session(engine) as db:
        bea = user_named(db, "bea@example.com")
        missing_id = db.scalar(select(Space.id).order_by(Space.id.desc())) + 1
        with pytest.raises(HTTPException) as foreign:
            member_space(foreign_id, bea, db)
        with pytest.raises(HTTPException) as missing:
            member_space(missing_id, bea, db)

    # 404 y no 403: la respuesta no revela que el espacio existe (RF-30).
    assert foreign.value.status_code == missing.value.status_code == 404
    assert foreign.value.detail == missing.value.detail
