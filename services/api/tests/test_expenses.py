from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from app import dates
from app.schemas import MAX_AMOUNT, ExpenseIn, ExpenseOut, ExpensePatch

# 2026-10-31 a las 20:00 en Bogotá (UTC-5): en UTC ya es 1 de noviembre.
NOW = datetime(2026, 11, 1, 1, 0, tzinfo=UTC)
TODAY = date(2026, 10, 31)

VALID = {"amount": 20000, "payment_type": "debit", "category_id": 1}


@pytest.fixture
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dates, "now", lambda: NOW)


def error_message(exc: pytest.ExceptionInfo[ValidationError]) -> str:
    """El mensaje del único error de validación."""
    errors = exc.value.errors()
    assert len(errors) == 1
    return errors[0]["msg"]


# --- Esquemas, sin HTTP (T3) ---


@pytest.mark.parametrize(
    "amount", [20000.0, "20000", True, 0, -1, MAX_AMOUNT + 1, None, [20000]]
)
def test_invalid_amount_is_rejected(amount: object) -> None:
    # RF-3: ni se acepta ni se redondea; `true` también es un `int` en Python.
    with pytest.raises(ValidationError):
        ExpenseIn.model_validate({**VALID, "amount": amount})


def test_max_amount_is_one_trillion_and_accepted() -> None:
    assert MAX_AMOUNT == 1_000_000_000_000
    assert ExpenseIn.model_validate({**VALID, "amount": MAX_AMOUNT}).amount == (
        MAX_AMOUNT
    )


def test_amount_over_max_names_the_max() -> None:
    with pytest.raises(ValidationError) as exc:
        ExpenseIn.model_validate({**VALID, "amount": MAX_AMOUNT + 1})
    assert str(MAX_AMOUNT) in error_message(exc)


def test_amount_with_decimals_says_it_must_be_whole() -> None:
    with pytest.raises(ValidationError) as exc:
        ExpenseIn.model_validate({**VALID, "amount": 20000.0})
    assert "entero" in error_message(exc)


def test_amount_survives_json_without_conversion() -> None:
    # Desde JSON llega igual que por HTTP: `20000.0` sigue siendo un decimal.
    with pytest.raises(ValidationError):
        ExpenseIn.model_validate_json(
            '{"amount": 20000.0, "payment_type": "debit", "category_id": 1}'
        )
    expense = ExpenseIn.model_validate_json(
        '{"amount": 20000, "payment_type": "debit", "category_id": 1}'
    )
    assert expense.amount == 20000


@pytest.mark.parametrize("payment_type", ["credit", "debit"])
def test_valid_payment_types(payment_type: str) -> None:
    expense = ExpenseIn.model_validate({**VALID, "payment_type": payment_type})
    assert expense.payment_type == payment_type


def test_invalid_payment_type_names_the_allowed_values() -> None:
    # RF-4.
    with pytest.raises(ValidationError) as exc:
        ExpenseIn.model_validate({**VALID, "payment_type": "efectivo"})
    message = error_message(exc)
    assert "credit" in message
    assert "debit" in message


@pytest.mark.parametrize("category_id", ["1", True, 1.0])
def test_category_id_must_be_an_integer(category_id: object) -> None:
    with pytest.raises(ValidationError):
        ExpenseIn.model_validate({**VALID, "category_id": category_id})


@pytest.mark.usefixtures("fixed_clock")
def test_spent_on_defaults_to_today_in_tz() -> None:
    # RF-2: el día de hoy en `TZ`, no en UTC.
    assert ExpenseIn.model_validate(VALID).spent_on == TODAY


@pytest.mark.usefixtures("fixed_clock")
def test_spent_on_today_is_accepted_and_tomorrow_rejected() -> None:
    # RF-6.
    today = ExpenseIn.model_validate({**VALID, "spent_on": "2026-10-31"})
    assert today.spent_on == TODAY

    with pytest.raises(ValidationError) as exc:
        ExpenseIn.model_validate({**VALID, "spent_on": "2026-11-01"})
    assert "posterior" in error_message(exc)


@pytest.mark.parametrize(
    "spent_on", ["2026-10-1", "2026-02-30", "2026-10-01T00:00:00", "ayer", 1761868800]
)
def test_spent_on_must_be_a_real_yyyy_mm_dd_day(spent_on: object) -> None:
    with pytest.raises(ValidationError) as exc:
        ExpenseIn.model_validate({**VALID, "spent_on": spent_on})
    assert "AAAA-MM-DD" in error_message(exc)


def test_description_is_stripped() -> None:
    # RF-7.
    expense = ExpenseIn.model_validate({**VALID, "description": "  café  "})
    assert expense.description == "café"


@pytest.mark.parametrize("description", ["", "   ", None])
def test_empty_description_becomes_none(description: str | None) -> None:
    expense = ExpenseIn.model_validate({**VALID, "description": description})
    assert expense.description is None


def test_description_without_it_is_none() -> None:
    assert ExpenseIn.model_validate(VALID).description is None


def test_description_up_to_200_characters() -> None:
    expense = ExpenseIn.model_validate({**VALID, "description": "a" * 200})
    assert expense.description == "a" * 200

    with pytest.raises(ValidationError) as exc:
        ExpenseIn.model_validate({**VALID, "description": "a" * 201})
    assert "200" in error_message(exc)


@pytest.mark.parametrize("field", ["amount", "payment_type", "category_id"])
def test_expense_in_requires_field(field: str) -> None:
    body = {key: value for key, value in VALID.items() if key != field}
    with pytest.raises(ValidationError):
        ExpenseIn.model_validate(body)


def test_space_and_author_in_input_are_ignored() -> None:
    # RF-14: el espacio sale de la ruta y el autor, de la sesión.
    body = {**VALID, "space_id": 99, "created_by": 99}
    expense = ExpenseIn.model_validate(body)
    patch = ExpensePatch.model_validate(body)

    for schema in (expense, patch):
        assert "space_id" not in schema.model_dump()
        assert "created_by" not in schema.model_dump()


def test_patch_only_contains_sent_fields() -> None:
    # RF-13: lo que no se envía no cambia.
    patch = ExpensePatch.model_validate({"amount": 15000})
    assert patch.model_fields_set == {"amount"}
    assert ExpensePatch.model_validate({}).model_fields_set == set()


@pytest.mark.parametrize("description", [None, "", "   "])
def test_patch_can_remove_description(description: str | None) -> None:
    # Decisión 8: nula, vacía o solo espacios la quitan.
    patch = ExpensePatch.model_validate({"description": description})
    assert patch.model_fields_set == {"description"}
    assert patch.description is None


@pytest.mark.parametrize("field", ["amount", "payment_type", "category_id", "spent_on"])
def test_patch_rejects_null_in_required_fields(field: str) -> None:
    # Un gasto no puede quedarse sin monto, tipo de pago, categoría ni fecha.
    with pytest.raises(ValidationError) as exc:
        ExpensePatch.model_validate({field: None})
    assert "no lo envíes" in error_message(exc)


@pytest.mark.usefixtures("fixed_clock")
@pytest.mark.parametrize(
    "body",
    [
        {"amount": 20000.0},
        {"amount": MAX_AMOUNT + 1},
        {"payment_type": "efectivo"},
        {"category_id": "1"},
        {"spent_on": "2026-11-01"},
        {"description": "a" * 201},
    ],
)
def test_patch_applies_the_same_validations(body: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ExpensePatch.model_validate(body)


@pytest.mark.usefixtures("fixed_clock")
def test_patch_accepts_valid_values() -> None:
    patch = ExpensePatch.model_validate(
        {
            "amount": 15000,
            "payment_type": "credit",
            "category_id": 2,
            "spent_on": "2026-10-30",
            "description": "  pan ",
        }
    )
    assert patch.amount == 15000
    assert patch.payment_type == "credit"
    assert patch.category_id == 2
    assert patch.spent_on == date(2026, 10, 30)
    assert patch.description == "pan"


def test_expense_out_has_exactly_the_planned_fields() -> None:
    # RF-8: todos los campos, incluido quién lo registró; sin `space_id`, que
    # ya está en la ruta.
    assert set(ExpenseOut.model_fields) == {
        "id",
        "amount",
        "payment_type",
        "category_id",
        "spent_on",
        "description",
        "created_by",
        "created_at",
    }
