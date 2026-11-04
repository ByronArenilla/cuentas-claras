from collections.abc import Callable
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from pydantic import ValidationError
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app import dates
from app.deps import INVALID_PERIOD
from app.models import Budget, Expense
from app.routers import budgets
from app.schemas import MAX_AMOUNT, BudgetIn

Login = Callable[..., dict[str, str]]

# 2026-10-31 a las 20:00 en Bogotá (UTC-5): en UTC ya es 1 de noviembre.
NOW = datetime(2026, 11, 1, 1, 0, tzinfo=UTC)

VALID = {"period": "2026-10", "amount": 400_000}


@pytest.fixture
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dates, "now", lambda: NOW)


def error_message(exc: pytest.ExceptionInfo[ValidationError]) -> str:
    """El mensaje del único error de validación."""
    errors = exc.value.errors()
    assert len(errors) == 1
    return errors[0]["msg"]


# --- Esquemas, sin HTTP (T2) ---


@pytest.mark.parametrize(
    "amount", [400_000.0, "400000", True, 0, -1, MAX_AMOUNT + 1, [400_000]]
)
def test_invalid_budget_amount_is_rejected(amount: object) -> None:
    # RF-7: las mismas reglas que el monto de un gasto; nada se redondea.
    with pytest.raises(ValidationError):
        BudgetIn.model_validate({**VALID, "amount": amount})


def test_budget_amount_over_max_names_the_max() -> None:
    with pytest.raises(ValidationError) as exc:
        BudgetIn.model_validate({**VALID, "amount": MAX_AMOUNT + 1})
    assert str(MAX_AMOUNT) in error_message(exc)


def test_budget_amount_of_one_trillion_is_accepted() -> None:
    assert BudgetIn.model_validate({**VALID, "amount": MAX_AMOUNT}).amount == (
        MAX_AMOUNT
    )


def test_null_amount_is_accepted_and_removes_the_budget() -> None:
    # RF-6, decisión 4: quitar el presupuesto es fijarlo sin monto.
    assert BudgetIn.model_validate({**VALID, "amount": None}).amount is None


def test_missing_amount_is_rejected() -> None:
    # Un cuerpo sin `amount` no puede quitar el presupuesto por accidente
    # (plan 004): quitarlo exige escribir `"amount": null`.
    with pytest.raises(ValidationError):
        BudgetIn.model_validate({"period": "2026-10"})


@pytest.mark.parametrize(
    "period", ["2026-13", "2026-00", "2026-1", "26-10", "octubre", "2026-10-01", 202610]
)
def test_invalid_period_is_rejected_with_the_expected_format(period: object) -> None:
    # RF-8, con el mismo mensaje que el listado de gastos (plan 004).
    with pytest.raises(ValidationError) as exc:
        BudgetIn.model_validate({**VALID, "period": period})
    assert error_message(exc) == INVALID_PERIOD.detail


@pytest.mark.parametrize("period", ["1990-01", "2030-12"])
def test_any_valid_period_is_accepted(period: str) -> None:
    # RF-10, decisión 3: pasado, actual o futuro.
    assert BudgetIn.model_validate({**VALID, "period": period}).period == period


@pytest.mark.usefixtures("fixed_clock")
def test_period_defaults_to_the_current_one_in_tz() -> None:
    # RF-2: en Bogotá todavía es 31 de octubre, aunque en UTC ya sea noviembre.
    assert BudgetIn.model_validate({"amount": 400_000}).period == "2026-10"


# --- Fijar y quitar el presupuesto (T4) ---


def personal_space(client: TestClient, headers: dict[str, str]) -> int:
    """Id del espacio personal, el único que tiene un usuario recién registrado."""
    [space] = client.get("/spaces", headers=headers).json()
    return space["id"]


def category_ids(
    client: TestClient, headers: dict[str, str], space_id: int
) -> dict[str, int]:
    """Ids de las categorías del espacio por nombre."""
    response = client.get(f"/spaces/{space_id}/categories", headers=headers)
    return {category["name"]: category["id"] for category in response.json()}


AnaSpace = tuple[int, dict[str, int], dict[str, str]]


@pytest.fixture
def ana_space(client: TestClient, login: Login) -> AnaSpace:
    """Espacio personal de Ana: (id, categorías por nombre, cabecera)."""
    ana = login("ana@example.com")
    space_id = personal_space(client, ana)
    return space_id, category_ids(client, ana, space_id), ana


def put_budget(
    client: TestClient,
    headers: dict[str, str],
    space_id: int,
    category_id: int,
    body: object,
) -> Response:
    return client.put(
        f"/spaces/{space_id}/budgets/{category_id}", json=body, headers=headers
    )


def stored_budgets(engine: Engine) -> list[tuple[int, date, int | None]]:
    """Filas de `budgets` como (categoría, desde, monto), en orden de inserción."""
    with Session(engine) as db:
        rows = db.execute(
            select(Budget.category_id, Budget.starts_on, Budget.amount).order_by(
                Budget.id
            )
        )
        return [tuple(row) for row in rows]


def test_setting_a_budget_returns_it(client: TestClient, ana_space: AnaSpace) -> None:
    # RF-1.
    space_id, categories, ana = ana_space
    body = {"period": "2026-10", "amount": 400_000}

    response = put_budget(client, ana, space_id, categories["Comida"], body)

    assert response.status_code == 200
    assert response.json() == {
        "category_id": categories["Comida"],
        "period": "2026-10",
        "amount": 400_000,
    }


def test_the_budget_is_stored_from_the_first_day_of_the_period(
    client: TestClient, engine: Engine, ana_space: AnaSpace
) -> None:
    space_id, categories, ana = ana_space
    body = {"period": "2026-10", "amount": 400_000}

    put_budget(client, ana, space_id, categories["Comida"], body)

    assert stored_budgets(engine) == [
        (categories["Comida"], date(2026, 10, 1), 400_000)
    ]


def test_setting_the_same_period_twice_keeps_one_row_with_the_last_amount(
    client: TestClient, engine: Engine, ana_space: AnaSpace
) -> None:
    # RF-5: `PUT` deja el mismo estado aunque se repita.
    space_id, categories, ana = ana_space
    comida = categories["Comida"]
    put_budget(client, ana, space_id, comida, {"period": "2026-10", "amount": 1})
    response = put_budget(
        client, ana, space_id, comida, {"period": "2026-10", "amount": 400_000}
    )

    assert response.status_code == 200
    assert stored_budgets(engine) == [(comida, date(2026, 10, 1), 400_000)]


def test_a_concurrent_insert_ends_as_an_update(
    client: TestClient,
    engine: Engine,
    ana_space: AnaSpace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # RF-5: si dos peticiones pasan la búsqueda previa a la vez, el índice
    # único frena la segunda y esta actualiza la fila de la primera. Se simula
    # que la búsqueda no vio la fila que ya existía.
    space_id, categories, ana = ana_space
    comida = categories["Comida"]
    put_budget(client, ana, space_id, comida, {"period": "2026-10", "amount": 1})
    real = budgets.find_budget
    calls: list[object] = []

    def misses_once(*args: object) -> Budget | None:
        calls.append(args)
        return None if len(calls) == 1 else real(*args)

    monkeypatch.setattr(budgets, "find_budget", misses_once)

    response = put_budget(
        client, ana, space_id, comida, {"period": "2026-10", "amount": 400_000}
    )

    assert response.status_code == 200
    assert response.json()["amount"] == 400_000
    assert stored_budgets(engine) == [(comida, date(2026, 10, 1), 400_000)]
    # Dos búsquedas: la previa, que no vio nada, y la de después del rollback.
    assert len(calls) == 2


def test_null_amount_removes_the_budget_without_touching_expenses(
    client: TestClient, engine: Engine, ana_space: AnaSpace
) -> None:
    # RF-6, decisión 4: sin confirmación y sin tocar gastos.
    space_id, categories, ana = ana_space
    comida = categories["Comida"]
    expense = {"amount": 20_000, "payment_type": "debit", "category_id": comida}
    client.post(f"/spaces/{space_id}/expenses", json=expense, headers=ana)
    put_budget(client, ana, space_id, comida, {"period": "2026-09", "amount": 1})

    response = put_budget(
        client, ana, space_id, comida, {"period": "2026-10", "amount": None}
    )

    assert response.status_code == 200
    assert response.json()["amount"] is None
    assert stored_budgets(engine)[-1] == (comida, date(2026, 10, 1), None)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Expense)) == 1


@pytest.mark.parametrize("period", ["1990-01", "2030-12"])
def test_budget_can_be_set_from_a_past_or_future_period(
    client: TestClient, ana_space: AnaSpace, period: str
) -> None:
    # RF-10, decisión 3.
    space_id, categories, ana = ana_space
    body = {"period": period, "amount": 400_000}

    response = put_budget(client, ana, space_id, categories["Comida"], body)

    assert response.status_code == 200
    assert response.json()["period"] == period


def test_unknown_category_is_not_found(
    client: TestClient, engine: Engine, ana_space: AnaSpace
) -> None:
    # RF-9.
    space_id, _, ana = ana_space

    response = put_budget(client, ana, space_id, 999, VALID)

    assert response.status_code == 404
    assert response.json()["detail"] == "Categoría no encontrada."
    assert stored_budgets(engine) == []


def test_category_of_another_space_is_not_found(
    client: TestClient, engine: Engine, login: Login, ana_space: AnaSpace
) -> None:
    # RF-9: igual que una inexistente, también cuando es de otro espacio de
    # Ana (criterio 7, que se amplía en `test_isolation.py`).
    space_id, _, ana = ana_space
    casa = client.post("/spaces", json={"name": "Casa"}, headers=ana).json()["id"]
    foreign = category_ids(client, ana, casa)["Comida"]

    response = put_budget(client, ana, space_id, foreign, VALID)

    assert response.status_code == 404
    assert response.json()["detail"] == "Categoría no encontrada."
    assert stored_budgets(engine) == []


@pytest.mark.parametrize(
    "body",
    [
        {**VALID, "amount": 400_000.0},
        {**VALID, "amount": "400000"},
        {**VALID, "amount": True},
        {**VALID, "amount": 0},
        {**VALID, "amount": -1},
        {**VALID, "amount": MAX_AMOUNT + 1},
        {"period": "2026-10"},
        {},
        {**VALID, "period": "2026-13"},
    ],
)
def test_invalid_body_changes_nothing(
    client: TestClient, engine: Engine, ana_space: AnaSpace, body: object
) -> None:
    # Criterio 5 (RF-7, RF-8): ni se guarda, ni se quita el que había.
    space_id, categories, ana = ana_space
    comida = categories["Comida"]
    put_budget(client, ana, space_id, comida, VALID)

    response = put_budget(client, ana, space_id, comida, body)

    assert response.status_code == 422
    assert stored_budgets(engine) == [(comida, date(2026, 10, 1), 400_000)]


@pytest.mark.usefixtures("fixed_clock")
def test_budget_without_period_rules_from_the_current_one_in_tz(
    client: TestClient, engine: Engine, ana_space: AnaSpace
) -> None:
    # Criterio 4, primera parte (RF-2): en Bogotá todavía es 31 de octubre.
    space_id, categories, ana = ana_space

    response = put_budget(
        client, ana, space_id, categories["Comida"], {"amount": 400_000}
    )

    assert response.json()["period"] == "2026-10"
    assert stored_budgets(engine)[0][1] == date(2026, 10, 1)


def test_setting_a_budget_without_session_is_rejected(
    client: TestClient, engine: Engine, ana_space: AnaSpace
) -> None:
    # RF-17.
    space_id, categories, _ = ana_space

    response = put_budget(client, {}, space_id, categories["Comida"], VALID)

    assert response.status_code == 401
    assert stored_budgets(engine) == []


# --- Resumen del periodo (T5) ---

SharedSpace = tuple[int, dict[str, str], dict[str, str]]


def get_summary(
    client: TestClient,
    headers: dict[str, str],
    space_id: int,
    period: str | None = None,
) -> Response:
    params = {} if period is None else {"period": period}
    return client.get(f"/spaces/{space_id}/summary", params=params, headers=headers)


def budget_in(
    client: TestClient,
    headers: dict[str, str],
    space_id: int,
    category_id: int,
    period: str,
) -> int | None:
    """Presupuesto vigente de la categoría según el resumen del periodo."""
    summary = get_summary(client, headers, space_id, period).json()
    [row] = [r for r in summary["categories"] if r["category_id"] == category_id]
    return row["budget"]


def test_summary_has_every_category_and_the_totals(
    client: TestClient, ana_space: AnaSpace
) -> None:
    # RF-11 a RF-14 por HTTP; el cálculo fino está en `test_summary.py`.
    space_id, categories, ana = ana_space
    comida, ocio = categories["Comida"], categories["Ocio"]
    put_budget(client, ana, space_id, comida, VALID)
    expense = {
        "amount": 412_000,
        "payment_type": "credit",
        "category_id": comida,
        "spent_on": "2026-10-15",
    }
    client.post(f"/spaces/{space_id}/expenses", json=expense, headers=ana)

    response = get_summary(client, ana, space_id, "2026-10")

    assert response.status_code == 200
    summary = response.json()
    assert summary["period"] == "2026-10"
    # Las siete predefinidas, en su orden (decisión 2).
    assert [row["name"] for row in summary["categories"]] == list(categories)
    rows = {row["category_id"]: row for row in summary["categories"]}
    assert rows[comida] == {
        "category_id": comida,
        "name": "Comida",
        "budget": 400_000,
        "spent": 412_000,
        "remaining": -12_000,
    }
    assert rows[ocio] == {
        "category_id": ocio,
        "name": "Ocio",
        "budget": None,
        "spent": 0,
        "remaining": None,
    }
    assert summary["total"] == {
        "budget": 400_000,
        "spent": 412_000,
        "remaining": -12_000,
    }


def test_budget_rules_onwards_and_changes_only_from_its_period(
    client: TestClient, ana_space: AnaSpace
) -> None:
    # Criterio 1 de punta a punta (RF-3, RF-4, RF-10).
    space_id, categories, ana = ana_space
    comida = categories["Comida"]

    put_budget(client, ana, space_id, comida, {"period": "2026-09", "amount": 400_000})

    assert budget_in(client, ana, space_id, comida, "2026-08") is None
    for period in ("2026-09", "2026-10", "2026-11", "2026-12"):
        assert budget_in(client, ana, space_id, comida, period) == 400_000

    put_budget(client, ana, space_id, comida, {"period": "2026-11", "amount": 500_000})

    assert budget_in(client, ana, space_id, comida, "2026-09") == 400_000
    assert budget_in(client, ana, space_id, comida, "2026-10") == 400_000
    assert budget_in(client, ana, space_id, comida, "2026-11") == 500_000
    assert budget_in(client, ana, space_id, comida, "2026-12") == 500_000


def test_removing_the_budget_rules_onwards_and_keeps_the_expenses(
    client: TestClient, ana_space: AnaSpace
) -> None:
    # Criterio 2 de punta a punta (RF-6).
    space_id, categories, ana = ana_space
    comida = categories["Comida"]
    put_budget(client, ana, space_id, comida, {"period": "2026-11", "amount": 500_000})
    expense = {
        "amount": 20_000,
        "payment_type": "debit",
        "category_id": comida,
        "spent_on": "2026-10-01",
    }
    client.post(f"/spaces/{space_id}/expenses", json=expense, headers=ana)
    expenses_before = client.get(
        f"/spaces/{space_id}/expenses", params={"period": "2026-10"}, headers=ana
    ).json()

    put_budget(client, ana, space_id, comida, {"period": "2026-12", "amount": None})

    assert budget_in(client, ana, space_id, comida, "2026-11") == 500_000
    assert budget_in(client, ana, space_id, comida, "2026-12") is None
    assert budget_in(client, ana, space_id, comida, "2027-01") is None
    expenses_after = client.get(
        f"/spaces/{space_id}/expenses", params={"period": "2026-10"}, headers=ana
    ).json()
    assert expenses_after == expenses_before


@pytest.mark.usefixtures("fixed_clock")
def test_summary_without_period_is_the_current_one_in_tz(
    client: TestClient, ana_space: AnaSpace
) -> None:
    # Criterio 4 completo (RF-2, RF-15): en Bogotá todavía es 31 de octubre.
    space_id, categories, ana = ana_space
    put_budget(client, ana, space_id, categories["Comida"], {"amount": 400_000})

    summary = get_summary(client, ana, space_id).json()

    assert summary["period"] == "2026-10"
    assert summary["total"]["budget"] == 400_000


@pytest.mark.parametrize("period", ["2026-13", "octubre", "2026-1", ""])
def test_invalid_summary_period_gets_the_same_message_as_the_expense_list(
    client: TestClient, ana_space: AnaSpace, period: str
) -> None:
    # RF-15.
    space_id, _, ana = ana_space

    summary = get_summary(client, ana, space_id, period)
    expenses = client.get(
        f"/spaces/{space_id}/expenses", params={"period": period}, headers=ana
    )

    assert summary.status_code == expenses.status_code == 422
    assert summary.json()["detail"] == expenses.json()["detail"]
    assert summary.json()["detail"] == INVALID_PERIOD.detail


def test_members_see_the_same_summary_and_change_each_others_budget(
    client: TestClient, shared_space: SharedSpace
) -> None:
    # Criterio 8 (RF-11, decisión 5).
    space_id, ana, bea = shared_space
    comida = category_ids(client, ana, space_id)["Comida"]
    put_budget(client, ana, space_id, comida, VALID)

    response = put_budget(
        client, bea, space_id, comida, {"period": "2026-10", "amount": 450_000}
    )

    assert response.status_code == 200
    seen_by_ana = get_summary(client, ana, space_id, "2026-10").json()
    seen_by_bea = get_summary(client, bea, space_id, "2026-10").json()
    assert seen_by_ana == seen_by_bea
    assert budget_in(client, ana, space_id, comida, "2026-10") == 450_000


def test_summary_without_session_is_rejected(
    client: TestClient, ana_space: AnaSpace
) -> None:
    # RF-17.
    space_id, _, _ = ana_space

    assert get_summary(client, {}, space_id, "2026-10").status_code == 401
