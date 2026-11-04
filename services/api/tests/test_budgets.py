from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app import dates
from app.routers.expenses import INVALID_PERIOD
from app.schemas import MAX_AMOUNT, BudgetIn

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
