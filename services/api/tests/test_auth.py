from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.models import Base, Invitation, Membership, Space, User
from app.security import verify_password
from tests.conftest import token_from

PASSWORD = "una-contraseña-larga"


def register(client: TestClient, email: str = "ana@example.com", **extra: str):
    return client.post(
        "/auth/register", json={"email": email, "password": PASSWORD, **extra}
    )


def count(engine: Engine, model: type[Base]) -> int:
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(model))


def row_counts(engine: Engine) -> tuple[int, int, int]:
    return count(engine, User), count(engine, Space), count(engine, Membership)


def test_registration_creates_user_space_and_membership(
    client: TestClient, engine: Engine
) -> None:
    response = register(client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "ana@example.com"
    assert body["personal_space"]["name"] == "Personal"
    with Session(engine) as db:
        user = db.scalars(select(User)).one()
        space = db.scalars(select(Space)).one()
        membership = db.scalars(select(Membership)).one()
    assert (user.id, space.id) == (body["id"], body["personal_space"]["id"])
    assert (membership.user_id, membership.space_id) == (user.id, space.id)


def test_password_is_stored_hashed(client: TestClient, engine: Engine) -> None:
    register(client)

    with Session(engine) as db:
        stored = db.scalars(select(User.password_hash)).one()
    assert stored != PASSWORD
    assert verify_password(stored, PASSWORD)


def test_response_never_includes_the_password_hash(
    client: TestClient, engine: Engine
) -> None:
    response = register(client)

    with Session(engine) as db:
        stored = db.scalars(select(User.password_hash)).one()
    assert "password" not in response.text
    assert stored not in response.text


def test_email_is_normalized_to_lowercase(client: TestClient) -> None:
    response = register(client, "  Ana@Example.COM ")

    assert response.json()["email"] == "ana@example.com"


def test_anyone_can_register_after_other_users_exist(
    client: TestClient, engine: Engine, login: Callable[[str], dict[str, str]]
) -> None:
    # RF-1: el registro es abierto, sin la excepción del primer usuario.
    login("ana@example.com")

    response = register(client, "bea@example.com")

    assert response.status_code == 201
    bea = response.json()
    with Session(engine) as db:
        spaces = db.scalars(
            select(Membership.space_id).where(Membership.user_id == bea["id"])
        ).all()
    assert spaces == [bea["personal_space"]["id"]]


def test_invitation_code_in_the_body_joins_no_space_and_stays_unused(
    client: TestClient, engine: Engine, login: Callable[[str], dict[str, str]]
) -> None:
    # Decisión 9: registrarse y unirse son dos pasos; el registro ignora el
    # código y la invitación sigue disponible para el canje (RF-17).
    ana = login("ana@example.com")
    space_id = client.post("/spaces", json={"name": "Casa"}, headers=ana).json()["id"]
    url = client.post(f"/spaces/{space_id}/invitations", headers=ana).json()["url"]

    response = register(client, "bea@example.com", invitation_code=token_from(url))

    assert response.status_code == 201
    bea = response.json()
    with Session(engine) as db:
        spaces = db.scalars(
            select(Membership.space_id).where(Membership.user_id == bea["id"])
        ).all()
        used_at = db.scalars(select(Invitation.used_at)).one()
    assert spaces == [bea["personal_space"]["id"]]
    assert used_at is None


def test_repeated_email_is_rejected_and_nothing_is_created(
    client: TestClient, engine: Engine, login: Callable[[str], dict[str, str]]
) -> None:
    login("ana@example.com")
    before = row_counts(engine)

    response = register(client, "ANA@example.com")

    assert response.status_code == 409
    assert "correo" in response.json()["detail"]
    assert row_counts(engine) == before


def test_short_password_is_rejected_naming_the_requirement(
    client: TestClient, engine: Engine
) -> None:
    response = client.post(
        "/auth/register", json={"email": "ana@example.com", "password": "corta"}
    )

    assert response.status_code == 422
    assert "12 caracteres" in response.text
    assert row_counts(engine) == (0, 0, 0)


def test_password_of_exactly_twelve_characters_is_accepted(
    client: TestClient,
) -> None:
    response = client.post(
        "/auth/register", json={"email": "ana@example.com", "password": "a" * 12}
    )

    assert response.status_code == 201


def test_malformed_email_is_rejected(client: TestClient, engine: Engine) -> None:
    for email in ("", "ana", "ana@", "@example.com", "ana@example", "a na@x.com"):
        response = register(client, email)

        assert response.status_code == 422, email
    assert row_counts(engine) == (0, 0, 0)
