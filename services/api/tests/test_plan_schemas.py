"""Esquemas de rubros, ingresos y copia del plan, sin HTTP (spec 008, T4)."""

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ValidationError

from app import dates
from app.schemas import (
    MAX_AMOUNT,
    BudgetItemIn,
    BudgetItemOut,
    BudgetItemPatch,
    IncomeIn,
    IncomeOut,
    IncomePatch,
    PlanCopyIn,
)

# 2026-10-31 a las 20:00 en Bogotá (UTC-5): en UTC ya es 1 de noviembre.
NOW = datetime(2026, 11, 1, 1, 0, tzinfo=UTC)

ITEM = {"period": "2026-11", "name": "Mercado", "category_id": 2, "amount": 800000}
INCOME = {"period": "2026-11", "name": "Salario", "amount": 5000000}
CASES: list[tuple[type[BaseModel], dict]] = [(BudgetItemIn, ITEM), (IncomeIn, INCOME)]


@pytest.fixture
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dates, "now", lambda: NOW)


def only_message(exc: pytest.ExceptionInfo[ValidationError]) -> str:
    errors = exc.value.errors()
    assert len(errors) == 1
    return errors[0]["msg"]


# --- Nombres (RF-3, RF-10) ---


@pytest.mark.parametrize(("model", "valid"), CASES)
def test_the_name_is_stored_without_surrounding_spaces(
    model: type[BaseModel], valid: dict
) -> None:
    assert model.model_validate({**valid, "name": "  Acción  "}).name == "Acción"


@pytest.mark.parametrize(("model", "valid"), CASES)
@pytest.mark.parametrize("name", ["", "   ", "x" * 51, None, 7])
def test_an_invalid_name_is_rejected(
    model: type[BaseModel], valid: dict, name: object
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate({**valid, "name": name})


def test_the_name_message_says_what_it_is_and_the_limit() -> None:
    with pytest.raises(ValidationError) as item:
        BudgetItemIn.model_validate({**ITEM, "name": " "})
    with pytest.raises(ValidationError) as income:
        IncomeIn.model_validate({**INCOME, "name": "x" * 51})

    assert only_message(item) == (
        "El nombre del rubro debe tener entre 1 y 50 caracteres."
    )
    assert only_message(income) == (
        "El nombre del ingreso debe tener entre 1 y 50 caracteres."
    )


@pytest.mark.parametrize(("model", "valid"), CASES)
def test_a_name_of_fifty_characters_is_accepted(
    model: type[BaseModel], valid: dict
) -> None:
    assert model.model_validate({**valid, "name": "x" * 50}).name == "x" * 50


# --- Montos (RF-4, criterio 7) ---


@pytest.mark.parametrize(("model", "valid"), CASES)
@pytest.mark.parametrize(
    "amount", [800000.0, "800000", True, 0, -1, MAX_AMOUNT + 1, None]
)
def test_an_invalid_amount_is_rejected(
    model: type[BaseModel], valid: dict, amount: object
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate({**valid, "amount": amount})


@pytest.mark.parametrize(("model", "valid"), CASES)
def test_one_trillion_is_accepted(model: type[BaseModel], valid: dict) -> None:
    assert model.model_validate({**valid, "amount": MAX_AMOUNT}).amount == MAX_AMOUNT


# --- Categoría del rubro ---


@pytest.mark.parametrize("category_id", [True, "2", 2.0, None])
def test_the_category_must_be_an_integer(category_id: object) -> None:
    with pytest.raises(ValidationError):
        BudgetItemIn.model_validate({**ITEM, "category_id": category_id})


def test_an_item_without_category_is_rejected() -> None:
    with pytest.raises(ValidationError):
        BudgetItemIn.model_validate(
            {key: value for key, value in ITEM.items() if key != "category_id"}
        )


# --- Periodo (RF-2, criterio 6) ---


@pytest.mark.parametrize(
    ("model", "valid"), [*CASES, (PlanCopyIn, {"period": "2026-11"})]
)
@pytest.mark.usefixtures("fixed_clock")
def test_without_period_the_current_one_is_used(
    model: type[BaseModel], valid: dict
) -> None:
    body = {key: value for key, value in valid.items() if key != "period"}

    assert model.model_validate(body).period == "2026-10"


@pytest.mark.parametrize(
    ("model", "valid"), [*CASES, (PlanCopyIn, {"period": "2026-11"})]
)
@pytest.mark.parametrize("period", ["2026-13", "2026-1", "noviembre", 202611])
def test_an_invalid_period_is_rejected_with_the_format(
    model: type[BaseModel], valid: dict, period: object
) -> None:
    with pytest.raises(ValidationError) as exc:
        model.model_validate({**valid, "period": period})

    assert "AAAA-MM" in only_message(exc)


@pytest.mark.parametrize(("model", "valid"), CASES)
@pytest.mark.parametrize("period", ["1990-01", "2030-12"])
def test_past_and_future_periods_are_accepted(
    model: type[BaseModel], valid: dict, period: str
) -> None:
    assert model.model_validate({**valid, "period": period}).period == period


# --- Editar (RF-6, RF-11, decisión 12) ---


@pytest.mark.parametrize("model", [BudgetItemPatch, IncomePatch])
def test_a_patch_only_keeps_what_was_sent(model: type[BaseModel]) -> None:
    patch = model.model_validate({"amount": 900000})

    assert patch.model_dump(exclude_unset=True) == {"amount": 900000}


@pytest.mark.parametrize(
    ("model", "field"),
    [
        (BudgetItemPatch, "name"),
        (BudgetItemPatch, "category_id"),
        (BudgetItemPatch, "amount"),
        (IncomePatch, "name"),
        (IncomePatch, "amount"),
    ],
)
def test_a_patch_rejects_null(model: type[BaseModel], field: str) -> None:
    with pytest.raises(ValidationError):
        model.model_validate({field: None})


@pytest.mark.parametrize("model", [BudgetItemPatch, IncomePatch])
def test_a_patch_cannot_change_the_period(model: type[BaseModel]) -> None:
    with pytest.raises(ValidationError) as exc:
        model.model_validate({"period": "2026-12"})

    assert "no se cambia" in only_message(exc)


def test_an_income_patch_has_no_category() -> None:
    assert "category_id" not in IncomePatch.model_fields


# --- Salidas ---


def test_outputs_show_the_period_as_a_month() -> None:
    # Se leen de la fila como el resto de las salidas: `period_start` (el día
    # 1) sale como `period` en formato `AAAA-MM`.
    item = BudgetItemOut.model_validate(
        SimpleNamespace(
            id=4,
            period_start=date(2026, 11, 1),
            name="Mercado",
            category_id=2,
            amount=800000,
        )
    )
    income = IncomeOut.model_validate(
        SimpleNamespace(
            id=1, period_start=date(2026, 11, 1), name="Salario", amount=5000000
        )
    )

    assert item.model_dump() == {
        "id": 4,
        "period": "2026-11",
        "name": "Mercado",
        "category_id": 2,
        "amount": 800000,
    }
    assert income.model_dump() == {
        "id": 1,
        "period": "2026-11",
        "name": "Salario",
        "amount": 5000000,
    }
