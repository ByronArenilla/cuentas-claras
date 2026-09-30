from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from app.config import load_settings
from app.main import app
from app.models import Invitation, Membership, User
from app.routers import invitations
from app.routers.invitations import claim_invitation, find_valid_invitation
from app.security import hash_token
from tests.conftest import WEB_BASE_URL, token_from

Login = Callable[..., dict[str, str]]


def invitation(engine: Engine, code: str) -> Invitation:
    with Session(engine) as db:
        return db.scalars(
            select(Invitation).where(Invitation.code_hash == hash_token(code))
        ).one()


def issue_space_invitation(
    client: TestClient, headers: dict[str, str], space_id: int
) -> str:
    response = client.post(f"/spaces/{space_id}/invitations", headers=headers)
    assert response.status_code == 201
    return token_from(response.json()["url"])


def create_space(client: TestClient, headers: dict[str, str], name: str) -> int:
    return client.post("/spaces", json={"name": name}, headers=headers).json()["id"]


def space_names(client: TestClient, headers: dict[str, str]) -> list[str]:
    return [space["name"] for space in client.get("/spaces", headers=headers).json()]


# --- Sin invitación de instancia (RF-16 retirado) ---


def test_instance_invitation_route_no_longer_exists() -> None:
    # Se comprueban las rutas publicadas y no un código HTTP: cuando exista
    # `GET /invitations/{token}` (T16), un POST aquí respondería 405 y no 404.
    # `app.routes` no sirve: agrupa cada router incluido en una sola entrada.
    paths = app.openapi()["paths"]

    assert "/invitations/{code}/redeem" in paths, "el test no ve las rutas"
    assert "/invitations/instance" not in paths


# --- Marca atómica del código (RF-19) ---


def test_a_code_can_only_be_claimed_once(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # Simula dos canjes simultáneos: ambos vieron el código vigente y los
    # dos intentan marcarlo; la segunda marca no debe afectar a ninguna fila.
    ana = login("ana@example.com")
    code = issue_space_invitation(client, ana, create_space(client, ana, "Casa"))
    with Session(engine) as db:
        row = find_valid_invitation(db, code)
        ana_id = db.scalars(select(User.id)).one()

        assert claim_invitation(db, row, ana_id) is True
        assert claim_invitation(db, row, ana_id) is False


# --- Invitación de espacio (RF-15, RF-17, RF-19, RF-20) ---


def test_space_invitation_is_stored_hashed_and_lasts_a_day(
    client: TestClient, engine: Engine, login: Login
) -> None:
    ana = login("ana@example.com")
    space_id = create_space(client, ana, "Casa")

    code = issue_space_invitation(client, ana, space_id)

    row = invitation(engine, code)
    assert row.code_hash != code
    assert (row.space_id, row.used_at) == (space_id, None)
    expected = datetime.now(UTC) + timedelta(hours=24)
    assert abs(row.expires_at - expected) < timedelta(minutes=1)


def test_sharing_returns_a_link_to_the_web(client: TestClient, login: Login) -> None:
    # RF-15: la API devuelve el enlace completo; el token solo viaja dentro.
    ana = login("ana@example.com")
    space_id = create_space(client, ana, "Casa")

    response = client.post(f"/spaces/{space_id}/invitations", headers=ana)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"url", "expires_at"}
    assert body["url"].startswith(f"{WEB_BASE_URL}/unirse/")
    assert token_from(body["url"])


def test_shared_links_do_not_repeat(client: TestClient, login: Login) -> None:
    ana = login("ana@example.com")
    space_id = create_space(client, ana, "Casa")

    tokens = {issue_space_invitation(client, ana, space_id) for _ in range(5)}

    assert len(tokens) == 5


def test_trailing_slash_in_web_base_url_does_not_double_it(
    client: TestClient, login: Login, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = load_settings(
        {"DATABASE_URL": "sqlite://", "TZ": "UTC", "WEB_BASE_URL": f"{WEB_BASE_URL}/"}
    )
    monkeypatch.setattr(invitations, "settings", configured)
    ana = login("ana@example.com")
    space_id = create_space(client, ana, "Casa")

    url = client.post(f"/spaces/{space_id}/invitations", headers=ana).json()["url"]

    assert url.startswith(f"{WEB_BASE_URL}/unirse/")
    assert "//unirse" not in url


def test_non_member_cannot_issue_space_invitations(
    client: TestClient, engine: Engine, login: Login
) -> None:
    ana, bea = login("ana@example.com"), login("bea@example.com")
    space_id = create_space(client, ana, "Casa")

    response = client.post(f"/spaces/{space_id}/invitations", headers=bea)

    # 404 como un espacio inexistente: Bea no sabe que "Casa" existe (RF-30).
    assert response.status_code == 404
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Invitation)) == 0


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
    assert invitation(engine, code).used_at is None


def test_unknown_code_cannot_be_redeemed(client: TestClient, login: Login) -> None:
    response = client.post("/invitations/codigo-inventado/redeem", headers=login())

    assert response.status_code == 403


def test_redeeming_requires_a_session(client: TestClient, login: Login) -> None:
    ana = login()
    code = issue_space_invitation(client, ana, create_space(client, ana, "Casa"))

    assert client.post(f"/invitations/{code}/redeem").status_code == 401


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


# --- Consultar la invitación sin sesión (RF-19, RF-36, RF-37) ---


def membership_count(engine: Engine) -> int:
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(Membership))


def test_previewing_shows_only_space_name_and_expiry(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # RF-36: sin cabecera Authorization, y nada más que nombre y caducidad
    # (ni id del espacio, ni miembros, ni quién invitó).
    ana = login("ana@example.com")
    code = issue_space_invitation(client, ana, create_space(client, ana, "Casa"))

    response = client.get(f"/invitations/{code}")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"space_name", "expires_at"}
    assert body["space_name"] == "Casa"
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert expires_at == invitation(engine, code).expires_at


def test_previewing_does_not_consume_the_invitation(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # Criterio de validación 5: consultar no gasta el enlace; canjear sí.
    ana, bea = login("ana@example.com"), login("bea@example.com")
    space_id = create_space(client, ana, "Casa")
    code = issue_space_invitation(client, ana, space_id)

    assert client.get(f"/invitations/{code}").status_code == 200
    assert client.get(f"/invitations/{code}").status_code == 200

    row = invitation(engine, code)
    assert (row.used_at, row.used_by) == (None, None)
    assert client.post(f"/invitations/{code}/redeem", headers=bea).status_code == 200


def test_previewing_never_creates_a_membership(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # RF-37: ni siquiera con sesión iniciada; unirse exige el canje explícito.
    ana, bea = login("ana@example.com"), login("bea@example.com")
    code = issue_space_invitation(client, ana, create_space(client, ana, "Casa"))
    before = membership_count(engine)

    client.get(f"/invitations/{code}")
    client.get(f"/invitations/{code}", headers=bea)

    assert membership_count(engine) == before
    assert space_names(client, bea) == ["Personal"]


def test_invalid_invitations_preview_as_404_with_the_same_message(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # RF-19: desconocido, usado y caducado son indistinguibles.
    ana, bea = login("ana@example.com"), login("bea@example.com")
    used = issue_space_invitation(client, ana, create_space(client, ana, "Casa"))
    client.post(f"/invitations/{used}/redeem", headers=bea).raise_for_status()
    expired = issue_space_invitation(client, ana, create_space(client, ana, "Viaje"))
    with Session(engine) as db:
        db.execute(
            update(Invitation)
            .where(Invitation.code_hash == hash_token(expired))
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        db.commit()

    responses = [
        client.get(f"/invitations/{code}")
        for code in ("codigo-inventado", used, expired)
    ]

    assert [response.status_code for response in responses] == [404, 404, 404]
    details = {response.json()["detail"] for response in responses}
    assert details == {invitations.INVITATION_INVALID}
