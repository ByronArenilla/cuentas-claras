from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from app.models import Invitation, Membership, Space, User
from app.routers.invitations import claim_invitation, find_valid_invitation
from app.security import hash_token
from tests.conftest import PASSWORD

Login = Callable[..., dict[str, str]]


def issue_instance_invitation(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post("/invitations/instance", headers=headers)
    assert response.status_code == 201
    return response.json()["code"]


def register(client: TestClient, email: str, code: str | None = None):
    body = {"email": email, "password": PASSWORD}
    if code is not None:
        body["invitation_code"] = code
    return client.post("/auth/register", json=body)


def invitation(engine: Engine, code: str) -> Invitation:
    with Session(engine) as db:
        return db.scalars(
            select(Invitation).where(Invitation.code_hash == hash_token(code))
        ).one()


def row_counts(engine: Engine) -> tuple[int, int, int]:
    with Session(engine) as db:
        return tuple(
            db.scalar(select(func.count()).select_from(model))
            for model in (User, Space, Membership)
        )


# --- Emitir la invitación de instancia (RF-16) ---


def test_instance_invitation_requires_a_session(client: TestClient) -> None:
    assert client.post("/invitations/instance").status_code == 401


def test_instance_invitation_is_stored_hashed_and_lasts_a_day(
    client: TestClient, engine: Engine, login: Login
) -> None:
    ana = login("ana@example.com")

    response = client.post("/invitations/instance", headers=ana)

    code = response.json()["code"]
    row = invitation(engine, code)
    assert row.code_hash != code
    assert (row.kind, row.space_id, row.used_at) == ("instance", None, None)
    expected = datetime.now(UTC) + timedelta(hours=24)
    assert abs(row.expires_at - expected) < timedelta(minutes=1)


def test_instance_invitation_codes_do_not_repeat(
    client: TestClient, login: Login
) -> None:
    ana = login("ana@example.com")

    codes = {issue_instance_invitation(client, ana) for _ in range(5)}

    assert len(codes) == 5


# --- Registro cerrado (RF-2, RF-19) ---


def test_registration_without_code_is_rejected_once_a_user_exists(
    client: TestClient, engine: Engine, login: Login
) -> None:
    login("ana@example.com")
    before = row_counts(engine)

    response = register(client, "bea@example.com")

    assert response.status_code == 403
    assert "invitación" in response.json()["detail"]
    assert row_counts(engine) == before


def test_registration_with_valid_code_works_and_uses_the_code(
    client: TestClient, engine: Engine, login: Login
) -> None:
    code = issue_instance_invitation(client, login("ana@example.com"))

    response = register(client, "bea@example.com", code)

    assert response.status_code == 201
    row = invitation(engine, code)
    assert row.used_at is not None
    assert row.used_by == response.json()["id"]


def test_instance_invitation_does_not_join_any_other_space(
    client: TestClient, engine: Engine, login: Login
) -> None:
    code = issue_instance_invitation(client, login("ana@example.com"))

    bea = register(client, "bea@example.com", code).json()

    with Session(engine) as db:
        spaces = db.scalars(
            select(Membership.space_id).where(Membership.user_id == bea["id"])
        ).all()
    assert spaces == [bea["personal_space"]["id"]]


def test_same_code_cannot_be_used_twice(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # Criterio de validación 5.
    code = issue_instance_invitation(client, login("ana@example.com"))
    register(client, "bea@example.com", code)
    before = row_counts(engine)

    response = register(client, "carla@example.com", code)

    assert response.status_code == 403
    assert row_counts(engine) == before


def test_expired_code_is_rejected(
    client: TestClient, engine: Engine, login: Login
) -> None:
    code = issue_instance_invitation(client, login("ana@example.com"))
    with Session(engine) as db:
        db.execute(
            update(Invitation).values(
                expires_at=datetime.now(UTC) - timedelta(seconds=1)
            )
        )
        db.commit()
    before = row_counts(engine)

    response = register(client, "bea@example.com", code)

    assert response.status_code == 403
    assert row_counts(engine) == before
    assert invitation(engine, code).used_at is None


def test_unknown_code_is_rejected(
    client: TestClient, engine: Engine, login: Login
) -> None:
    login("ana@example.com")
    before = row_counts(engine)

    response = register(client, "bea@example.com", "codigo-inventado")

    assert response.status_code == 403
    assert row_counts(engine) == before


def test_repeated_email_does_not_consume_the_code(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # RF-4: el registro rechazado no gasta el código; sigue sirviendo.
    code = issue_instance_invitation(client, login("ana@example.com"))

    assert register(client, "ana@example.com", code).status_code == 409
    assert invitation(engine, code).used_at is None
    assert register(client, "bea@example.com", code).status_code == 201


def test_first_registration_still_needs_no_code(client: TestClient) -> None:
    assert register(client, "ana@example.com").status_code == 201


def test_a_code_can_only_be_claimed_once(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # Simula dos registros simultáneos: ambos vieron el código vigente y los
    # dos intentan marcarlo; la segunda marca no debe afectar a ninguna fila.
    code = issue_instance_invitation(client, login("ana@example.com"))
    with Session(engine) as db:
        row = find_valid_invitation(db, code)
        ana_id = db.scalars(select(User.id)).one()

        assert claim_invitation(db, row, ana_id) is True
        assert claim_invitation(db, row, ana_id) is False


# --- Invitación de espacio (RF-15, RF-17, RF-18, RF-20) ---


def issue_space_invitation(
    client: TestClient, headers: dict[str, str], space_id: int
) -> str:
    response = client.post(f"/spaces/{space_id}/invitations", headers=headers)
    assert response.status_code == 201
    return response.json()["code"]


def create_space(client: TestClient, headers: dict[str, str], name: str) -> int:
    return client.post("/spaces", json={"name": name}, headers=headers).json()["id"]


def space_names(client: TestClient, headers: dict[str, str]) -> list[str]:
    return [space["name"] for space in client.get("/spaces", headers=headers).json()]


def test_space_invitation_is_stored_hashed_and_lasts_a_day(
    client: TestClient, engine: Engine, login: Login
) -> None:
    ana = login("ana@example.com")
    space_id = create_space(client, ana, "Casa")

    code = issue_space_invitation(client, ana, space_id)

    row = invitation(engine, code)
    assert row.code_hash != code
    assert (row.kind, row.space_id, row.used_at) == ("space", space_id, None)
    expected = datetime.now(UTC) + timedelta(hours=24)
    assert abs(row.expires_at - expected) < timedelta(minutes=1)


def test_non_member_cannot_issue_space_invitations(
    client: TestClient, engine: Engine, login: Login
) -> None:
    ana, bea = login("ana@example.com"), login("bea@example.com")
    space_id = create_space(client, ana, "Casa")

    response = client.post(f"/spaces/{space_id}/invitations", headers=bea)

    # 404 como un espacio inexistente: Bea no sabe que "Casa" existe (RF-30).
    assert response.status_code == 404
    with Session(engine) as db:
        space_invitations = select(func.count()).where(Invitation.kind == "space")
        assert db.scalar(space_invitations) == 0


def test_issuing_space_invitations_requires_a_session(
    client: TestClient, login: Login
) -> None:
    space_id = create_space(client, login(), "Casa")

    assert client.post(f"/spaces/{space_id}/invitations").status_code == 401


def test_redeeming_makes_the_user_a_member(
    client: TestClient, engine: Engine, login: Login
) -> None:
    ana, bea = login("ana@example.com"), login("bea@example.com")
    space_id = create_space(client, ana, "Casa")
    code = issue_space_invitation(client, ana, space_id)

    response = client.post(f"/invitations/{code}/redeem", headers=bea)

    assert response.status_code == 200
    assert response.json() == {"id": space_id, "name": "Casa"}
    assert space_names(client, bea) == ["Personal", "Casa"]
    row = invitation(engine, code)
    assert row.used_at is not None
    assert row.used_by == client.get("/me", headers=bea).json()["id"]


def test_space_code_cannot_be_redeemed_twice(client: TestClient, login: Login) -> None:
    # Criterio de validación 5.
    ana, bea = login("ana@example.com"), login("bea@example.com")
    carla = login("carla@example.com")
    space_id = create_space(client, ana, "Casa")
    code = issue_space_invitation(client, ana, space_id)
    client.post(f"/invitations/{code}/redeem", headers=bea)

    response = client.post(f"/invitations/{code}/redeem", headers=carla)

    assert response.status_code == 403
    assert space_names(client, carla) == ["Personal"]


def test_existing_member_is_rejected_and_code_stays_unused(
    client: TestClient, engine: Engine, login: Login
) -> None:
    ana, bea = login("ana@example.com"), login("bea@example.com")
    space_id = create_space(client, ana, "Casa")
    code = issue_space_invitation(client, ana, space_id)

    response = client.post(f"/invitations/{code}/redeem", headers=ana)

    assert response.status_code == 409
    assert invitation(engine, code).used_at is None
    assert client.post(f"/invitations/{code}/redeem", headers=bea).status_code == 200


def test_expired_space_code_is_rejected(
    client: TestClient, engine: Engine, login: Login
) -> None:
    ana, bea = login("ana@example.com"), login("bea@example.com")
    code = issue_space_invitation(client, ana, create_space(client, ana, "Casa"))
    with Session(engine) as db:
        db.execute(
            update(Invitation).values(
                expires_at=datetime.now(UTC) - timedelta(seconds=1)
            )
        )
        db.commit()

    response = client.post(f"/invitations/{code}/redeem", headers=bea)

    assert response.status_code == 403
    assert space_names(client, bea) == ["Personal"]


def test_unknown_code_cannot_be_redeemed(client: TestClient, login: Login) -> None:
    response = client.post("/invitations/codigo-inventado/redeem", headers=login())

    assert response.status_code == 403


def test_instance_code_cannot_be_redeemed_and_stays_unused(
    client: TestClient, engine: Engine, login: Login
) -> None:
    ana, bea = login("ana@example.com"), login("bea@example.com")
    code = issue_instance_invitation(client, ana)

    response = client.post(f"/invitations/{code}/redeem", headers=bea)

    assert response.status_code == 403
    assert invitation(engine, code).used_at is None


def test_redeeming_requires_a_session(client: TestClient, login: Login) -> None:
    ana = login()
    code = issue_space_invitation(client, ana, create_space(client, ana, "Casa"))

    assert client.post(f"/invitations/{code}/redeem").status_code == 401


def test_registering_with_space_code_creates_user_personal_space_and_membership(
    client: TestClient, engine: Engine, login: Login
) -> None:
    ana = login("ana@example.com")
    space_id = create_space(client, ana, "Casa")
    code = issue_space_invitation(client, ana, space_id)

    response = register(client, "bea@example.com", code)

    assert response.status_code == 201
    bea = response.json()
    with Session(engine) as db:
        spaces = db.scalars(
            select(Membership.space_id).where(Membership.user_id == bea["id"])
        ).all()
    assert set(spaces) == {bea["personal_space"]["id"], space_id}
    assert invitation(engine, code).used_by == bea["id"]


def test_shared_space_fixture_has_two_members(
    client: TestClient, shared_space: tuple[int, dict[str, str], dict[str, str]]
) -> None:
    space_id, ana, bea = shared_space

    assert (
        space_names(client, ana)
        == space_names(client, bea)
        == [
            "Personal",
            "Casa",
        ]
    )
