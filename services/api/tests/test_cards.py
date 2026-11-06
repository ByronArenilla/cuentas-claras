"""Rutas de tarjetas (spec 009, RF-1 a RF-8)."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.models import Card

Login = Callable[..., dict[str, str]]

VISA = {"name": "Visa", "cutoff_day": 25, "due_day": 10, "monthly_rate": 1.9}


def personal_space(client: TestClient, headers: dict[str, str]) -> int:
    return client.get("/spaces", headers=headers).json()[0]["id"]


def create_card(
    client: TestClient, headers: dict[str, str], space_id: int, **fields: object
) -> Response:
    return client.post(
        f"/spaces/{space_id}/cards", json={**VISA, **fields}, headers=headers
    )


def cards_in(engine: Engine) -> int:
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(Card))


def stored_card(engine: Engine, card_id: int) -> Card:
    with Session(engine) as db:
        return db.get_one(Card, card_id)


@pytest.fixture
def ana(client: TestClient, login: Login) -> tuple[dict[str, str], int]:
    headers = login("ana@example.com")
    return headers, personal_space(client, headers)


# --- Crear y validar (RF-1 a RF-3) ---


def test_creating_a_card_returns_it(client: TestClient, engine: Engine, ana) -> None:
    headers, space_id = ana

    response = create_card(client, headers, space_id, name="  Visa  ")

    assert response.status_code == 201
    body = response.json()
    assert body == {
        "id": body["id"],
        "name": "Visa",
        "cutoff_day": 25,
        "due_day": 10,
        "monthly_rate": 1.9,
        "deleted": False,
    }
    # 1,90 % se guarda como 190 puntos básicos: exacto, sin `float`.
    assert stored_card(engine, body["id"]).monthly_rate_bp == 190


def test_rate_is_kept_exact(client: TestClient, engine: Engine, ana) -> None:
    headers, space_id = ana

    body = create_card(client, headers, space_id, monthly_rate=1.89).json()

    assert body["monthly_rate"] == 1.89
    assert stored_card(engine, body["id"]).monthly_rate_bp == 189


def test_rate_is_optional(client: TestClient, ana) -> None:
    headers, space_id = ana
    fields = {key: value for key, value in VISA.items() if key != "monthly_rate"}

    response = client.post(f"/spaces/{space_id}/cards", json=fields, headers=headers)

    assert response.status_code == 201
    assert response.json()["monthly_rate"] is None


@pytest.mark.parametrize(
    "fields",
    [
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 51},
        {"cutoff_day": 0},
        {"cutoff_day": 32},
        {"cutoff_day": "5"},
        {"cutoff_day": 5.0},
        {"due_day": 0},
        {"due_day": 32},
        {"due_day": True},
        {"monthly_rate": 0},
        {"monthly_rate": 10.01},
        {"monthly_rate": 1.895},
        {"monthly_rate": -1},
        {"monthly_rate": "1.89"},
        {"monthly_rate": True},
    ],
)
def test_invalid_card_is_rejected(
    client: TestClient, engine: Engine, ana, fields: dict[str, object]
) -> None:
    headers, space_id = ana

    response = create_card(client, headers, space_id, **fields)

    assert response.status_code == 422
    assert cards_in(engine) == 0


def test_rate_limits_are_accepted(client: TestClient, ana) -> None:
    headers, space_id = ana

    low = create_card(client, headers, space_id, name="Baja", monthly_rate=0.01)
    high = create_card(client, headers, space_id, name="Alta", monthly_rate=10)

    assert (low.status_code, high.status_code) == (201, 201)
    assert high.json()["monthly_rate"] == 10


def test_equivalent_name_is_rejected_naming_the_existing_card(
    client: TestClient, engine: Engine, ana
) -> None:
    headers, space_id = ana
    create_card(client, headers, space_id)

    response = create_card(client, headers, space_id, name="visa")

    assert response.status_code == 409
    assert response.json()["detail"] == "Ya existe la tarjeta «Visa»."
    assert cards_in(engine) == 1


# --- Listar (RF-4) ---


def test_listing_returns_active_cards_in_creation_order(
    client: TestClient, ana
) -> None:
    headers, space_id = ana
    for name in ("Visa", "Master", "Amex"):
        create_card(client, headers, space_id, name=name)
    amex = client.get(f"/spaces/{space_id}/cards", headers=headers).json()[2]
    client.delete(f"/spaces/{space_id}/cards/{amex['id']}", headers=headers)

    listed = client.get(f"/spaces/{space_id}/cards", headers=headers).json()

    assert [card["name"] for card in listed] == ["Visa", "Master"]


# --- Editar (RF-5) ---


def test_editing_changes_only_what_is_sent(client: TestClient, ana) -> None:
    headers, space_id = ana
    card = create_card(client, headers, space_id).json()

    response = client.patch(
        f"/spaces/{space_id}/cards/{card['id']}",
        json={"cutoff_day": 5},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == {**card, "cutoff_day": 5}


def test_null_rate_removes_it(client: TestClient, engine: Engine, ana) -> None:
    headers, space_id = ana
    card = create_card(client, headers, space_id).json()

    response = client.patch(
        f"/spaces/{space_id}/cards/{card['id']}",
        json={"monthly_rate": None},
        headers=headers,
    )

    assert response.json()["monthly_rate"] is None
    assert stored_card(engine, card["id"]).monthly_rate_bp is None


@pytest.mark.parametrize("field", ["name", "cutoff_day", "due_day"])
def test_null_is_rejected_in_other_fields(client: TestClient, ana, field: str) -> None:
    headers, space_id = ana
    card = create_card(client, headers, space_id).json()

    response = client.patch(
        f"/spaces/{space_id}/cards/{card['id']}", json={field: None}, headers=headers
    )

    assert response.status_code == 422


def test_renaming_to_an_equivalent_name_is_rejected(client: TestClient, ana) -> None:
    headers, space_id = ana
    create_card(client, headers, space_id, name="Master")
    card = create_card(client, headers, space_id).json()

    response = client.patch(
        f"/spaces/{space_id}/cards/{card['id']}",
        json={"name": "MASTER"},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Ya existe la tarjeta «Master»."


def test_renaming_a_card_to_its_own_name_works(client: TestClient, ana) -> None:
    headers, space_id = ana
    card = create_card(client, headers, space_id).json()

    response = client.patch(
        f"/spaces/{space_id}/cards/{card['id']}",
        json={"name": "VISA"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "VISA"


def test_an_archived_card_can_be_edited(client: TestClient, ana) -> None:
    headers, space_id = ana
    card = create_card(client, headers, space_id).json()
    client.delete(f"/spaces/{space_id}/cards/{card['id']}", headers=headers)

    response = client.patch(
        f"/spaces/{space_id}/cards/{card['id']}",
        json={"monthly_rate": 2},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["monthly_rate"] == 2
    assert response.json()["deleted"] is True


# --- Eliminar y restaurar (RF-6, RF-7) ---


def test_deleting_archives_the_card_with_a_notice(
    client: TestClient, engine: Engine, ana
) -> None:
    headers, space_id = ana
    card = create_card(client, headers, space_id).json()

    response = client.delete(f"/spaces/{space_id}/cards/{card['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "id": card["id"],
        "name": "Visa",
        "message": "Eliminaste «Visa». Sus cuotas pendientes siguen llegando a "
        "Deudas. Para volver a usarla en compras nuevas, créala de nuevo con el "
        "mismo nombre.",
    }
    assert client.get(f"/spaces/{space_id}/cards", headers=headers).json() == []
    assert stored_card(engine, card["id"]).deleted_at is not None


def test_creating_an_archived_name_restores_the_original_card(
    client: TestClient, engine: Engine, ana
) -> None:
    headers, space_id = ana
    card = create_card(client, headers, space_id).json()
    client.delete(f"/spaces/{space_id}/cards/{card['id']}", headers=headers)

    # Otros días y otra tasa: se restaura como era (decisión 24).
    response = create_card(
        client, headers, space_id, name="VISA", cutoff_day=1, due_day=2, monthly_rate=3
    )

    assert response.status_code == 200
    assert response.json() == card
    assert cards_in(engine) == 1
    listed = client.get(f"/spaces/{space_id}/cards", headers=headers).json()
    assert listed == [card]


# --- No encontrada (RF-8) ---


def test_missing_card_is_not_found(client: TestClient, ana) -> None:
    headers, space_id = ana
    url = f"/spaces/{space_id}/cards/999"

    for response in (
        client.patch(url, json={"cutoff_day": 5}, headers=headers),
        client.delete(url, headers=headers),
    ):
        assert response.status_code == 404
        assert response.json()["detail"] == "Tarjeta no encontrada."


def test_deleting_an_archived_card_is_not_found(client: TestClient, ana) -> None:
    headers, space_id = ana
    card = create_card(client, headers, space_id).json()
    url = f"/spaces/{space_id}/cards/{card['id']}"
    client.delete(url, headers=headers)

    assert client.delete(url, headers=headers).status_code == 404


def test_a_card_of_another_space_is_not_found(
    client: TestClient, login: Login, ana
) -> None:
    headers, space_id = ana
    card = create_card(client, headers, space_id).json()
    # Ana es miembro de los dos espacios: la tarjeta sigue sin verse desde el
    # otro (RF-8).
    other = client.post("/spaces", json={"name": "Viajes"}, headers=headers).json()
    url = f"/spaces/{other['id']}/cards/{card['id']}"

    assert client.patch(url, json={"cutoff_day": 5}, headers=headers).status_code == 404
    assert client.delete(url, headers=headers).status_code == 404


def test_cards_need_a_session(client: TestClient, ana) -> None:
    _, space_id = ana

    assert client.get(f"/spaces/{space_id}/cards").status_code == 401
    assert client.post(f"/spaces/{space_id}/cards", json=VISA).status_code == 401
