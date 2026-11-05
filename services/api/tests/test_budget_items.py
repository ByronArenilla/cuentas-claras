"""Rutas de rubros: crear, editar y borrar (spec 008, RF-1 a RF-9)."""

from collections.abc import Callable
from datetime import date

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.models import BudgetItem, Expense

Login = Callable[..., dict[str, str]]
SharedSpace = tuple[int, dict[str, str], dict[str, str]]


def personal_space(client: TestClient, headers: dict[str, str]) -> int:
    return client.get("/spaces", headers=headers).json()[0]["id"]


def category(client: TestClient, headers: dict[str, str], space_id: int, name: str):
    listed = client.get(f"/spaces/{space_id}/categories", headers=headers).json()
    [found] = [c["id"] for c in listed if c["name"] == name]
    return found


def create_item(
    client: TestClient, headers: dict[str, str], space_id: int, **fields: object
) -> Response:
    body = {"period": "2026-11", "name": "Mercado", "amount": 800000, **fields}
    if "category_id" not in body:
        body["category_id"] = category(client, headers, space_id, "Comida")
    return client.post(f"/spaces/{space_id}/budget-items", json=body, headers=headers)


def items_in(engine: Engine) -> int:
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(BudgetItem))


def add_expense(engine: Engine, item: dict, space_id: int, user_id: int = 1) -> int:
    """Gasto ligado al rubro, guardado directamente: la ruta de gastos todavía
    no acepta rubros (T7)."""
    with Session(engine) as db:
        expense = Expense(
            space_id=space_id,
            category_id=item["category_id"],
            budget_item_id=item["id"],
            created_by=user_id,
            amount=412000,
            payment_type="debit",
            spent_on=date(2026, 11, 3),
            description="Mercado de la semana",
        )
        db.add(expense)
        db.commit()
        return expense.id


def stored_expense(engine: Engine, expense_id: int) -> Expense:
    with Session(engine) as db:
        return db.get_one(Expense, expense_id)


@pytest.fixture
def ana(client: TestClient, login: Login) -> tuple[dict[str, str], int]:
    headers = login("ana@example.com")
    return headers, personal_space(client, headers)


# --- Crear (RF-1 a RF-5) ---


def test_creating_an_item_returns_it(client: TestClient, ana) -> None:
    headers, space_id = ana
    comida = category(client, headers, space_id, "Comida")

    response = create_item(client, headers, space_id)

    assert response.status_code == 201
    assert response.json() == {
        "id": response.json()["id"],
        "period": "2026-11",
        "name": "Mercado",
        "category_id": comida,
        "amount": 800000,
    }


@pytest.mark.parametrize("period", ["2020-01", "2031-12"])
def test_past_and_future_months_are_accepted(
    client: TestClient, ana, period: str
) -> None:
    headers, space_id = ana

    response = create_item(client, headers, space_id, period=period)

    assert response.status_code == 201
    assert response.json()["period"] == period


@pytest.mark.parametrize("name", ["mercado", " MERCADO ", "Mércado"])
def test_an_equivalent_name_clashes_in_the_same_month(
    client: TestClient, engine: Engine, ana, name: str
) -> None:
    # Criterio 2: nombra el rubro que ya existe, con su escritura.
    headers, space_id = ana
    create_item(client, headers, space_id)

    response = create_item(client, headers, space_id, name=name)

    assert response.status_code == 409
    assert response.json()["detail"] == "Ya existe el rubro «Mercado» en 2026-11."
    assert items_in(engine) == 1


def test_accents_do_not_make_a_different_name(client: TestClient, ana) -> None:
    # Decisión 22: "accion" choca con "Acción".
    headers, space_id = ana
    create_item(client, headers, space_id, name="Acción")

    response = create_item(client, headers, space_id, name="accion")

    assert response.status_code == 409
    assert "«Acción»" in response.json()["detail"]


def test_the_same_name_is_allowed_in_another_month_or_space(
    client: TestClient, login: Login, ana
) -> None:
    headers, space_id = ana
    bea = login("bea@example.com")
    create_item(client, headers, space_id)

    other_month = create_item(client, headers, space_id, period="2026-12")
    other_space = create_item(client, bea, personal_space(client, bea))

    assert other_month.status_code == 201
    assert other_space.status_code == 201


def test_a_category_of_another_space_is_rejected(
    client: TestClient, engine: Engine, login: Login, ana
) -> None:
    # RF-5: igual que una inexistente.
    headers, space_id = ana
    bea = login("bea@example.com")
    foreign = category(client, bea, personal_space(client, bea), "Comida")

    for category_id in (foreign, 999_999):
        response = create_item(client, headers, space_id, category_id=category_id)
        assert response.status_code == 422
        assert response.json()["detail"] == "La categoría no existe en este espacio."
    assert items_in(engine) == 0


def test_a_deleted_category_is_rejected(
    client: TestClient, engine: Engine, ana
) -> None:
    # RF-41.
    headers, space_id = ana
    ocio = category(client, headers, space_id, "Ocio")
    client.delete(f"/spaces/{space_id}/categories/{ocio}", headers=headers)

    response = create_item(client, headers, space_id, category_id=ocio)

    assert response.status_code == 422
    assert "«Ocio» fue eliminada" in response.json()["detail"]
    assert items_in(engine) == 0


def test_creating_without_a_session_is_rejected(
    client: TestClient, engine: Engine, ana
) -> None:
    headers, space_id = ana
    comida = category(client, headers, space_id, "Comida")

    response = create_item(client, {}, space_id, category_id=comida)

    assert response.status_code == 401
    assert items_in(engine) == 0


# --- Editar (RF-6, RF-7, RF-42) ---


def patch(
    client: TestClient, headers: dict[str, str], space_id: int, item_id: int, body
) -> Response:
    return client.patch(
        f"/spaces/{space_id}/budget-items/{item_id}", json=body, headers=headers
    )


def test_editing_changes_only_what_was_sent(client: TestClient, ana) -> None:
    headers, space_id = ana
    item = create_item(client, headers, space_id).json()

    response = patch(client, headers, space_id, item["id"], {"amount": 900000})

    assert response.status_code == 200
    assert response.json() == {**item, "amount": 900000}


def test_editing_the_name_checks_the_month(client: TestClient, ana) -> None:
    headers, space_id = ana
    create_item(client, headers, space_id, name="Arriendo")
    item = create_item(client, headers, space_id).json()

    clash = patch(client, headers, space_id, item["id"], {"name": "ARRIENDO"})
    own = patch(client, headers, space_id, item["id"], {"name": "MERCADO"})

    assert clash.status_code == 409
    assert clash.json()["detail"] == "Ya existe el rubro «Arriendo» en 2026-11."
    # Cambiar solo las mayúsculas del propio nombre no choca consigo mismo.
    assert own.status_code == 200
    assert own.json()["name"] == "MERCADO"


def test_the_period_cannot_be_changed(client: TestClient, ana) -> None:
    headers, space_id = ana
    item = create_item(client, headers, space_id).json()

    response = patch(client, headers, space_id, item["id"], {"period": "2026-12"})

    assert response.status_code == 422
    again = patch(client, headers, space_id, item["id"], {})
    assert again.json()["period"] == "2026-11"


def test_changing_the_category_moves_its_expenses(
    client: TestClient, engine: Engine, ana
) -> None:
    # Criterio 5, RF-7.
    headers, space_id = ana
    hogar = category(client, headers, space_id, "Hogar")
    item = create_item(client, headers, space_id).json()
    expense_id = add_expense(engine, item, space_id)

    response = patch(client, headers, space_id, item["id"], {"category_id": hogar})

    assert response.json()["category_id"] == hogar
    assert stored_expense(engine, expense_id).category_id == hogar


def test_a_category_change_to_a_deleted_or_foreign_one_is_rejected(
    client: TestClient, engine: Engine, login: Login, ana
) -> None:
    headers, space_id = ana
    item = create_item(client, headers, space_id).json()
    expense_id = add_expense(engine, item, space_id)
    ocio = category(client, headers, space_id, "Ocio")
    client.delete(f"/spaces/{space_id}/categories/{ocio}", headers=headers)
    bea = login("bea@example.com")
    foreign = category(client, bea, personal_space(client, bea), "Hogar")

    deleted = patch(client, headers, space_id, item["id"], {"category_id": ocio})
    other = patch(client, headers, space_id, item["id"], {"category_id": foreign})

    assert deleted.status_code == 422
    assert other.status_code == 422
    assert stored_expense(engine, expense_id).category_id == item["category_id"]


def test_an_item_whose_category_was_deleted_can_still_be_edited(
    client: TestClient, ana
) -> None:
    # RF-42, decisión 17.
    headers, space_id = ana
    item = create_item(client, headers, space_id).json()
    client.delete(
        f"/spaces/{space_id}/categories/{item['category_id']}", headers=headers
    )

    response = patch(
        client,
        headers,
        space_id,
        item["id"],
        {"name": "Mercado grande", "amount": 1, "category_id": item["category_id"]},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Mercado grande"


# --- Borrar (RF-8) ---


def test_deleting_an_item_keeps_its_expenses_unplanned(
    client: TestClient, engine: Engine, ana
) -> None:
    # Criterio 5, decisión 8: sin confirmación, y el gasto queda igual salvo
    # el rubro.
    headers, space_id = ana
    item = create_item(client, headers, space_id).json()
    expense_id = add_expense(engine, item, space_id)
    before = stored_expense(engine, expense_id)

    response = client.delete(
        f"/spaces/{space_id}/budget-items/{item['id']}", headers=headers
    )

    assert response.status_code == 204
    after = stored_expense(engine, expense_id)
    assert after.budget_item_id is None
    assert after.category_id == before.category_id == item["category_id"]
    assert (after.amount, after.spent_on, after.payment_type) == (
        before.amount,
        before.spent_on,
        before.payment_type,
    )
    assert (after.description, after.created_by) == (
        before.description,
        before.created_by,
    )
    assert items_in(engine) == 0


# --- Rubro de la ruta (RF-9) ---


def test_a_missing_or_foreign_item_is_404(
    client: TestClient, engine: Engine, login: Login, ana
) -> None:
    headers, space_id = ana
    bea = login("bea@example.com")
    foreign = create_item(client, bea, personal_space(client, bea)).json()["id"]

    for item_id in (foreign, 999_999):
        url = f"/spaces/{space_id}/budget-items/{item_id}"
        edited = client.patch(url, json={"amount": 1}, headers=headers)
        deleted = client.delete(url, headers=headers)
        for response in (edited, deleted):
            assert response.status_code == 404
            assert response.json()["detail"] == "Rubro no encontrado."
    assert items_in(engine) == 1


def test_a_member_edits_what_another_member_created(
    client: TestClient, shared_space: SharedSpace
) -> None:
    space_id, ana, bea = shared_space
    item = create_item(client, ana, space_id).json()

    response = patch(client, bea, space_id, item["id"], {"amount": 1})

    assert response.status_code == 200
