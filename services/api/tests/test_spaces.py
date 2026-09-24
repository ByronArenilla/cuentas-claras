from collections.abc import Callable

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.deps import member_space
from app.models import Invitation, Membership, Space, User
from app.security import hash_token

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


# --- Salir de un espacio (RF-21, RF-22, RF-35) ---

SharedSpace = tuple[int, dict[str, str], dict[str, str]]


def leave(client: TestClient, headers: dict[str, str], space_id: int):
    return client.delete(f"/spaces/{space_id}/members/me", headers=headers)


def test_member_leaves_and_stops_seeing_the_space(
    client: TestClient, shared_space: SharedSpace
) -> None:
    space_id, ana, bea = shared_space

    response = leave(client, bea, space_id)

    assert response.status_code == 204
    assert names(client, bea) == ["Personal"]


def test_space_stays_for_the_remaining_members(
    client: TestClient, engine: Engine, shared_space: SharedSpace
) -> None:
    # Principio 8: salir no borra el espacio ni sus datos.
    space_id, ana, bea = shared_space

    leave(client, bea, space_id)

    assert names(client, ana) == ["Personal", "Casa"]
    with Session(engine) as db:
        assert db.get(Space, space_id) is not None


def test_last_member_cannot_leave_and_is_told_to_delete(
    client: TestClient, engine: Engine, login: Login
) -> None:
    ana = login()
    space_id = create_space(client, ana, "Viajes")["id"]

    response = leave(client, ana, space_id)

    assert response.status_code == 409
    assert "bórralo" in response.json()["detail"]
    assert names(client, ana) == ["Personal", "Viajes"]


def test_nobody_leaves_their_only_space(
    client: TestClient, engine: Engine, shared_space: SharedSpace
) -> None:
    # Bea queda solo en "Casa", compartido con Ana: aunque no es la última
    # miembro, es su único espacio (RF-35).
    space_id, ana, bea = shared_space
    bea_id = client.get("/me", headers=bea).json()["id"]
    with Session(engine) as db:
        personal = db.scalar(
            select(Membership).where(
                Membership.user_id == bea_id, Membership.space_id != space_id
            )
        )
        db.delete(personal)
        db.commit()

    response = leave(client, bea, space_id)

    assert response.status_code == 409
    assert "único espacio" in response.json()["detail"]
    assert names(client, bea) == ["Casa"]


def test_only_space_message_wins_over_last_member(
    client: TestClient, login: Login
) -> None:
    # Con un solo espacio y siendo su única miembro, "bórralo" no sería una
    # salida: RF-26 también impide borrar el único espacio.
    ana = login()
    [personal] = client.get("/spaces", headers=ana).json()

    response = leave(client, ana, personal["id"])

    assert response.status_code == 409
    assert "único espacio" in response.json()["detail"]


def test_leaving_a_foreign_space_is_404(
    client: TestClient, shared_space: SharedSpace, login: Login
) -> None:
    space_id, ana, bea = shared_space
    carla = login("carla@example.com")

    assert leave(client, carla, space_id).status_code == 404
    assert names(client, ana) == ["Personal", "Casa"]


def test_leaving_requires_a_session(
    client: TestClient, shared_space: SharedSpace
) -> None:
    space_id, ana, bea = shared_space

    assert client.delete(f"/spaces/{space_id}/members/me").status_code == 401
    assert names(client, bea) == ["Personal", "Casa"]


# --- Borrar un espacio (RF-23 a RF-27) ---


def delete_space(
    client: TestClient, headers: dict[str, str], space_id: int, confirm: str
):
    return client.delete(
        f"/spaces/{space_id}", params={"confirm": confirm}, headers=headers
    )


def test_sole_member_deletes_confirming_the_exact_name(
    client: TestClient, engine: Engine, login: Login
) -> None:
    ana = login()
    space_id = create_space(client, ana, "Viajes")["id"]

    response = delete_space(client, ana, space_id, "Viajes")

    assert response.status_code == 204
    assert names(client, ana) == ["Personal"]
    with Session(engine) as db:
        assert db.get(Space, space_id) is None
        assert (
            db.scalars(select(Membership).where(Membership.space_id == space_id)).all()
            == []
        )


@pytest.mark.parametrize("confirm", ["Viaje", "viajes", "Viajes ", ""])
def test_wrong_confirmation_deletes_nothing(
    client: TestClient, login: Login, confirm: str
) -> None:
    ana = login()
    space_id = create_space(client, ana, "Viajes")["id"]

    response = delete_space(client, ana, space_id, confirm)

    assert response.status_code == 400
    assert "nombre" in response.json()["detail"]
    assert names(client, ana) == ["Personal", "Viajes"]


def test_missing_confirmation_deletes_nothing(client: TestClient, login: Login) -> None:
    ana = login()
    space_id = create_space(client, ana, "Viajes")["id"]

    response = client.delete(f"/spaces/{space_id}", headers=ana)

    assert response.status_code == 422
    assert names(client, ana) == ["Personal", "Viajes"]


def test_space_with_several_members_cannot_be_deleted(
    client: TestClient, shared_space: SharedSpace
) -> None:
    space_id, ana, bea = shared_space

    response = delete_space(client, ana, space_id, "Casa")

    assert response.status_code == 409
    assert names(client, ana) == names(client, bea) == ["Personal", "Casa"]


def test_only_space_cannot_be_deleted(client: TestClient, login: Login) -> None:
    ana = login()
    [personal] = client.get("/spaces", headers=ana).json()

    response = delete_space(client, ana, personal["id"], "Personal")

    assert response.status_code == 409
    assert "único espacio" in response.json()["detail"]
    assert names(client, ana) == ["Personal"]


def test_deleting_a_space_leaves_the_user_and_other_spaces_intact(
    client: TestClient, engine: Engine, shared_space: SharedSpace
) -> None:
    # Criterio de validación 6 (RF-27): Ana borra "Viajes" y nada más cambia.
    casa_id, ana, bea = shared_space
    viajes_id = create_space(client, ana, "Viajes")["id"]
    casa_code = client.post(f"/spaces/{casa_id}/invitations", headers=ana).json()

    delete_space(client, ana, viajes_id, "Viajes")

    assert client.get("/me", headers=ana).status_code == 200
    assert names(client, ana) == names(client, bea) == ["Personal", "Casa"]
    with Session(engine) as db:
        casa_members = db.scalars(
            select(Membership).where(Membership.space_id == casa_id)
        ).all()
        casa_invitation = db.scalar(
            select(Invitation).where(
                Invitation.code_hash == hash_token(casa_code["code"])
            )
        )
    assert len(casa_members) == 2
    assert casa_invitation is not None


def test_pending_invitations_die_with_the_space(
    client: TestClient, login: Login
) -> None:
    ana, bea = login("ana@example.com"), login("bea@example.com")
    space_id = create_space(client, ana, "Viajes")["id"]
    code = client.post(f"/spaces/{space_id}/invitations", headers=ana).json()["code"]

    delete_space(client, ana, space_id, "Viajes")

    assert client.post(f"/invitations/{code}/redeem", headers=bea).status_code == 403
    assert names(client, bea) == ["Personal"]


def test_deleting_a_foreign_space_is_404(client: TestClient, login: Login) -> None:
    ana, bea = login("ana@example.com"), login("bea@example.com")
    space_id = create_space(client, ana, "Viajes")["id"]

    assert delete_space(client, bea, space_id, "Viajes").status_code == 404
    assert names(client, ana) == ["Personal", "Viajes"]


def test_deleting_requires_a_session(client: TestClient, login: Login) -> None:
    ana = login()
    space_id = create_space(client, ana, "Viajes")["id"]

    response = client.delete(f"/spaces/{space_id}", params={"confirm": "Viajes"})

    assert response.status_code == 401
    assert names(client, ana) == ["Personal", "Viajes"]
