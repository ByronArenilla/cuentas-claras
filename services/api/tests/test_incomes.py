"""Rutas de ingresos: crear, editar y borrar (spec 008, RF-10 a RF-12)."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.models import Income

Login = Callable[..., dict[str, str]]
SharedSpace = tuple[int, dict[str, str], dict[str, str]]


def personal_space(client: TestClient, headers: dict[str, str]) -> int:
    return client.get("/spaces", headers=headers).json()[0]["id"]


def create_income(
    client: TestClient, headers: dict[str, str], space_id: int, **fields: object
) -> Response:
    body = {"period": "2026-11", "name": "Salario", "amount": 5000000, **fields}
    return client.post(f"/spaces/{space_id}/incomes", json=body, headers=headers)


def incomes_in(engine: Engine) -> int:
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(Income))


@pytest.fixture
def ana(client: TestClient, login: Login) -> tuple[dict[str, str], int]:
    headers = login("ana@example.com")
    return headers, personal_space(client, headers)


# --- Crear (RF-10) ---


def test_creating_an_income_returns_it(client: TestClient, ana) -> None:
    headers, space_id = ana

    response = create_income(client, headers, space_id)

    assert response.status_code == 201
    assert response.json() == {
        "id": response.json()["id"],
        "period": "2026-11",
        "name": "Salario",
        "amount": 5000000,
    }


@pytest.mark.parametrize(
    ("existing", "name"), [("Salario", "salario"), ("Bonificación", "bonificacion")]
)
def test_an_equivalent_name_clashes_in_the_same_month(
    client: TestClient, engine: Engine, ana, existing: str, name: str
) -> None:
    # Criterio 2 y decisión 22.
    headers, space_id = ana
    create_income(client, headers, space_id, name=existing)

    response = create_income(client, headers, space_id, name=name)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        f"Ya existe el ingreso «{existing}» en 2026-11."
    )
    assert incomes_in(engine) == 1


def test_the_same_name_is_allowed_in_another_month_or_space(
    client: TestClient, login: Login, ana
) -> None:
    headers, space_id = ana
    bea = login("bea@example.com")
    create_income(client, headers, space_id)

    assert create_income(client, headers, space_id, period="2026-12").status_code == (
        201
    )
    assert create_income(client, bea, personal_space(client, bea)).status_code == 201


def test_invalid_data_is_rejected_without_saving(
    client: TestClient, engine: Engine, ana
) -> None:
    headers, space_id = ana

    for fields in ({"amount": 0}, {"amount": 1.5}, {"name": " "}, {"period": "x"}):
        assert create_income(client, headers, space_id, **fields).status_code == 422
    assert incomes_in(engine) == 0


def test_creating_without_a_session_is_rejected(
    client: TestClient, engine: Engine, ana
) -> None:
    _, space_id = ana

    assert create_income(client, {}, space_id).status_code == 401
    assert incomes_in(engine) == 0


# --- Editar y borrar (RF-11) ---


def patch(
    client: TestClient, headers: dict[str, str], space_id: int, income_id: int, body
) -> Response:
    return client.patch(
        f"/spaces/{space_id}/incomes/{income_id}", json=body, headers=headers
    )


def test_editing_changes_only_what_was_sent(client: TestClient, ana) -> None:
    headers, space_id = ana
    income = create_income(client, headers, space_id).json()

    response = patch(client, headers, space_id, income["id"], {"amount": 5200000})

    assert response.status_code == 200
    assert response.json() == {**income, "amount": 5200000}


def test_editing_the_name_checks_the_month(client: TestClient, ana) -> None:
    headers, space_id = ana
    create_income(client, headers, space_id, name="Arriendo cobrado")
    income = create_income(client, headers, space_id).json()

    clash = patch(client, headers, space_id, income["id"], {"name": "arriendo COBRADO"})
    own = patch(client, headers, space_id, income["id"], {"name": "SALARIO"})

    assert clash.status_code == 409
    assert "«Arriendo cobrado»" in clash.json()["detail"]
    assert own.status_code == 200


def test_the_period_cannot_be_changed(client: TestClient, ana) -> None:
    headers, space_id = ana
    income = create_income(client, headers, space_id).json()

    response = patch(client, headers, space_id, income["id"], {"period": "2026-12"})

    assert response.status_code == 422


def test_deleting_needs_no_confirmation(
    client: TestClient, engine: Engine, ana
) -> None:
    headers, space_id = ana
    income = create_income(client, headers, space_id).json()

    response = client.delete(
        f"/spaces/{space_id}/incomes/{income['id']}", headers=headers
    )

    assert response.status_code == 204
    assert incomes_in(engine) == 0


# --- Ingreso de la ruta (RF-12) ---


def test_a_missing_or_foreign_income_is_404(
    client: TestClient, engine: Engine, login: Login, ana
) -> None:
    headers, space_id = ana
    bea = login("bea@example.com")
    foreign = create_income(client, bea, personal_space(client, bea)).json()["id"]

    for income_id in (foreign, 999_999):
        url = f"/spaces/{space_id}/incomes/{income_id}"
        for response in (
            client.patch(url, json={"amount": 1}, headers=headers),
            client.delete(url, headers=headers),
        ):
            assert response.status_code == 404
            assert response.json()["detail"] == "Ingreso no encontrado."
    assert incomes_in(engine) == 1


def test_a_member_edits_what_another_member_created(
    client: TestClient, shared_space: SharedSpace
) -> None:
    space_id, ana, bea = shared_space
    income = create_income(client, ana, space_id).json()

    assert patch(client, bea, space_id, income["id"], {"amount": 1}).status_code == (
        200
    )
