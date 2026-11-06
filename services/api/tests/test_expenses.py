from collections.abc import Callable
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app import dates
from app.models import Expense
from app.schemas import MAX_AMOUNT, ExpenseIn, ExpenseOut, ExpensePatch

Login = Callable[..., dict[str, str]]

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


@pytest.mark.parametrize(
    ("payment_type", "extra"),
    [
        # Desde la 009, un gasto a crédito lleva tarjeta y descripción.
        ("credit", {"card_id": 1, "description": "Compra TV"}),
        ("debit", {}),
    ],
)
def test_valid_payment_types(payment_type: str, extra: dict[str, object]) -> None:
    expense = ExpenseIn.model_validate({**VALID, "payment_type": payment_type, **extra})
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
        # Spec 008: el rubro del gasto, nulo si no estaba planeado (RF-20).
        "budget_item_id",
        # Spec 009: tarjeta, cuotas y mes de la primera cuota, nulos si no es
        # una compra con tarjeta (RF-18).
        "card_id",
        "installments",
        "first_due_period",
        # Spec 010: deuda o gasto del mes; nulo sin tarjeta (RF-4).
        "is_debt",
    }


# --- Registrar (T4) ---


def personal_space(client: TestClient, headers: dict[str, str]) -> int:
    """Id del espacio personal, el único que tiene un usuario recién registrado."""
    [space] = client.get("/spaces", headers=headers).json()
    return space["id"]


def first_category(client: TestClient, headers: dict[str, str], space_id: int) -> int:
    """Id de la primera categoría predefinida del espacio ("Hogar")."""
    response = client.get(f"/spaces/{space_id}/categories", headers=headers)
    return response.json()[0]["id"]


def count_expenses(engine: Engine) -> int:
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(Expense))


@pytest.fixture
def ana_space(client: TestClient, login: Login) -> tuple[int, int, dict[str, str]]:
    """Espacio personal de Ana: (id del espacio, id de una categoría, cabecera)."""
    ana = login("ana@example.com")
    space_id = personal_space(client, ana)
    return space_id, first_category(client, ana, space_id), ana


AnaSpace = tuple[int, int, dict[str, str]]


@pytest.mark.usefixtures("fixed_clock")
def test_registering_returns_the_expense_with_its_author(
    client: TestClient, ana_space: AnaSpace
) -> None:
    # RF-1 y RF-8: se guarda en el espacio y con quien lo registró.
    space_id, category_id, ana = ana_space
    ana_id = client.get("/me", headers=ana).json()["id"]
    body = {
        "amount": 20000,
        "payment_type": "debit",
        "category_id": category_id,
        "spent_on": "2026-10-30",
        "description": "  mercado ",
    }

    response = client.post(f"/spaces/{space_id}/expenses", json=body, headers=ana)

    assert response.status_code == 201
    expense = response.json()
    assert set(expense) == set(ExpenseOut.model_fields)
    assert isinstance(expense["id"], int)
    assert expense["amount"] == 20000
    assert expense["payment_type"] == "debit"
    assert expense["category_id"] == category_id
    assert expense["spent_on"] == "2026-10-30"
    assert expense["description"] == "mercado"
    assert expense["created_by"] == ana_id
    assert expense["created_at"]


def test_registered_expense_is_stored_in_the_route_space(
    client: TestClient, engine: Engine, ana_space: AnaSpace
) -> None:
    space_id, category_id, ana = ana_space
    body = {**VALID, "category_id": category_id, "space_id": space_id + 1000}

    expense_id = client.post(
        f"/spaces/{space_id}/expenses", json=body, headers=ana
    ).json()["id"]

    with Session(engine) as db:
        assert db.get_one(Expense, expense_id).space_id == space_id


@pytest.mark.usefixtures("fixed_clock")
def test_expense_without_date_falls_on_today_in_tz(
    client: TestClient, ana_space: AnaSpace
) -> None:
    # Criterio 4: el 31 de octubre a las 20:00 en Bogotá ya es 1 de
    # noviembre en UTC, y el gasto debe caer en octubre (RF-2).
    space_id, category_id, ana = ana_space
    body = {**VALID, "category_id": category_id}

    response = client.post(f"/spaces/{space_id}/expenses", json=body, headers=ana)

    assert response.status_code == 201
    assert response.json()["spent_on"] == "2026-10-31"


def test_category_of_another_space_or_missing_is_rejected(
    client: TestClient, engine: Engine, login: Login, ana_space: AnaSpace
) -> None:
    # RF-5: una categoría de otro espacio cuenta como inexistente.
    space_id, _, ana = ana_space
    bea = login("bea@example.com")
    bea_space = personal_space(client, bea)
    foreign = first_category(client, bea, bea_space)

    for category_id in (foreign, foreign + 1000):
        body = {**VALID, "category_id": category_id}
        response = client.post(f"/spaces/{space_id}/expenses", json=body, headers=ana)

        assert response.status_code == 422
        assert response.json()["detail"] == "La categoría no existe en este espacio."
    assert count_expenses(engine) == 0


@pytest.mark.parametrize(
    "amount", [20000.0, "20000", True, 0, -1, MAX_AMOUNT + 1, None]
)
def test_invalid_amount_is_rejected_and_nothing_is_stored(
    client: TestClient, engine: Engine, ana_space: AnaSpace, amount: object
) -> None:
    # Criterio 5 (RF-3).
    space_id, category_id, ana = ana_space
    body = {**VALID, "category_id": category_id, "amount": amount}

    response = client.post(f"/spaces/{space_id}/expenses", json=body, headers=ana)

    assert response.status_code == 422
    assert count_expenses(engine) == 0


@pytest.mark.usefixtures("fixed_clock")
@pytest.mark.parametrize(
    "change",
    [
        {"payment_type": "efectivo"},
        {"spent_on": "2026-11-01"},
        {"description": "a" * 201},
    ],
)
def test_other_invalid_fields_are_rejected_and_nothing_is_stored(
    client: TestClient, engine: Engine, ana_space: AnaSpace, change: dict[str, object]
) -> None:
    # RF-4, RF-6 y RF-7.
    space_id, category_id, ana = ana_space
    body = {**VALID, "category_id": category_id, **change}

    response = client.post(f"/spaces/{space_id}/expenses", json=body, headers=ana)

    assert response.status_code == 422
    assert count_expenses(engine) == 0


def test_registering_without_session_is_rejected(
    client: TestClient, engine: Engine, ana_space: AnaSpace
) -> None:
    space_id, category_id, _ = ana_space
    body = {**VALID, "category_id": category_id}

    response = client.post(f"/spaces/{space_id}/expenses", json=body)

    assert response.status_code == 401
    assert count_expenses(engine) == 0


# --- Consultar y listar (T5) ---

# Mediados de noviembre en Bogotá: todos los días de octubre y el 1 de
# noviembre ya pasaron.
MID_NOVEMBER = datetime(2026, 11, 15, 17, 0, tzinfo=UTC)


@pytest.fixture
def mid_november(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dates, "now", lambda: MID_NOVEMBER)


def add_expense(
    client: TestClient,
    headers: dict[str, str],
    space_id: int,
    category_id: int,
    spent_on: str,
    amount: int = 20000,
) -> dict[str, object]:
    """Registra un gasto por la API y devuelve la respuesta."""
    body = {**VALID, "category_id": category_id, "spent_on": spent_on}
    body["amount"] = amount
    response = client.post(f"/spaces/{space_id}/expenses", json=body, headers=headers)
    response.raise_for_status()
    return response.json()


def listed(
    client: TestClient, headers: dict[str, str], space_id: int, **params: str
) -> list[dict[str, object]]:
    response = client.get(
        f"/spaces/{space_id}/expenses", params=params, headers=headers
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.usefixtures("mid_november")
def test_expense_is_read_with_all_its_fields(
    client: TestClient, ana_space: AnaSpace
) -> None:
    # RF-8.
    space_id, category_id, ana = ana_space
    created = add_expense(client, ana, space_id, category_id, "2026-10-15")

    response = client.get(f"/spaces/{space_id}/expenses/{created['id']}", headers=ana)

    assert response.status_code == 200
    assert response.json() == created


def test_missing_expense_is_not_found(client: TestClient, ana_space: AnaSpace) -> None:
    space_id, _, ana = ana_space

    response = client.get(f"/spaces/{space_id}/expenses/1000", headers=ana)

    assert response.status_code == 404
    assert response.json()["detail"] == "Gasto no encontrado."


@pytest.mark.usefixtures("mid_november")
def test_period_includes_its_first_and_last_day_only(
    client: TestClient, ana_space: AnaSpace
) -> None:
    # RF-9: del 1 al 31 de octubre, ni un día más.
    space_id, category_id, ana = ana_space
    days = ["2026-09-30", "2026-10-01", "2026-10-31", "2026-11-01"]
    for day in days:
        add_expense(client, ana, space_id, category_id, day)

    expenses = listed(client, ana, space_id, period="2026-10")

    assert [expense["spent_on"] for expense in expenses] == ["2026-10-31", "2026-10-01"]


@pytest.mark.usefixtures("mid_november")
def test_list_is_newest_day_first_and_latest_registered_first(
    client: TestClient, ana_space: AnaSpace
) -> None:
    # Decisión 5: a igual día, el registrado después va primero.
    space_id, category_id, ana = ana_space
    first = add_expense(client, ana, space_id, category_id, "2026-10-10", 1)
    older = add_expense(client, ana, space_id, category_id, "2026-10-02", 2)
    second = add_expense(client, ana, space_id, category_id, "2026-10-10", 3)
    newest = add_expense(client, ana, space_id, category_id, "2026-10-20", 4)

    ids = [expense["id"] for expense in listed(client, ana, space_id, period="2026-10")]

    assert ids == [newest["id"], second["id"], first["id"], older["id"]]


def test_list_without_period_uses_the_current_month_in_tz(
    client: TestClient, ana_space: AnaSpace, monkeypatch: pytest.MonkeyPatch
) -> None:
    # RF-10: el 31 de octubre a las 20:00 en Bogotá el mes actual es octubre,
    # aunque en UTC ya sea noviembre.
    space_id, category_id, ana = ana_space
    monkeypatch.setattr(dates, "now", lambda: MID_NOVEMBER)
    add_expense(client, ana, space_id, category_id, "2026-11-01")
    october = add_expense(client, ana, space_id, category_id, "2026-10-31")
    monkeypatch.setattr(dates, "now", lambda: NOW)

    assert [expense["id"] for expense in listed(client, ana, space_id)] == [
        october["id"]
    ]


@pytest.mark.parametrize("period", ["2026-13", "octubre", "2026-1", ""])
def test_invalid_period_is_rejected_with_the_expected_format(
    client: TestClient, ana_space: AnaSpace, period: str
) -> None:
    # RF-11.
    space_id, _, ana = ana_space

    response = client.get(
        f"/spaces/{space_id}/expenses", params={"period": period}, headers=ana
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "El periodo debe tener el formato AAAA-MM, por ejemplo 2026-10."
    )


@pytest.mark.usefixtures("mid_november")
def test_members_of_the_same_space_get_the_same_list(
    client: TestClient, shared_space: tuple[int, dict[str, str], dict[str, str]]
) -> None:
    # Parte del criterio 3: lo que registra cada uno lo ven los dos.
    space_id, ana, bea = shared_space
    category_id = first_category(client, ana, space_id)
    add_expense(client, ana, space_id, category_id, "2026-10-05")
    add_expense(client, bea, space_id, category_id, "2026-10-06")

    ana_list = listed(client, ana, space_id, period="2026-10")

    assert len(ana_list) == 2
    assert ana_list == listed(client, bea, space_id, period="2026-10")
    assert len({expense["created_by"] for expense in ana_list}) == 2


# --- Editar (T6) ---


def patch_expense(
    client: TestClient,
    headers: dict[str, str],
    space_id: int,
    expense_id: object,
    body: dict[str, object],
) -> object:
    return client.patch(
        f"/spaces/{space_id}/expenses/{expense_id}", json=body, headers=headers
    )


def read(
    client: TestClient, headers: dict[str, str], space_id: int, expense_id: object
) -> dict[str, object]:
    return client.get(
        f"/spaces/{space_id}/expenses/{expense_id}", headers=headers
    ).json()


@pytest.fixture
def ana_expense(
    client: TestClient, ana_space: AnaSpace, mid_november: None
) -> tuple[int, dict[str, str], dict[str, object]]:
    """Un gasto de Ana con descripción: (id del espacio, cabecera, gasto)."""
    space_id, category_id, ana = ana_space
    body = {
        **VALID,
        "category_id": category_id,
        "spent_on": "2026-10-15",
        "description": "mercado",
    }
    response = client.post(f"/spaces/{space_id}/expenses", json=body, headers=ana)
    return space_id, ana, response.json()


AnaExpense = tuple[int, dict[str, str], dict[str, object]]


def test_patching_only_amount_keeps_the_rest(
    client: TestClient, ana_expense: AnaExpense
) -> None:
    # RF-13.
    space_id, ana, expense = ana_expense

    response = patch_expense(client, ana, space_id, expense["id"], {"amount": 15000})

    assert response.status_code == 200
    assert response.json() == {**expense, "amount": 15000}
    assert read(client, ana, space_id, expense["id"]) == {**expense, "amount": 15000}


@pytest.mark.parametrize("description", [None, ""])
def test_patching_null_or_empty_description_removes_it(
    client: TestClient, ana_expense: AnaExpense, description: str | None
) -> None:
    # Decisión 8.
    space_id, ana, expense = ana_expense

    body = {"description": description}
    response = patch_expense(client, ana, space_id, expense["id"], body)

    assert response.status_code == 200
    assert read(client, ana, space_id, expense["id"])["description"] is None


def test_not_sending_description_keeps_it(
    client: TestClient, ana_expense: AnaExpense
) -> None:
    space_id, ana, expense = ana_expense

    patch_expense(client, ana, space_id, expense["id"], {"amount": 15000})

    assert read(client, ana, space_id, expense["id"])["description"] == "mercado"


def test_empty_patch_changes_nothing(
    client: TestClient, ana_expense: AnaExpense
) -> None:
    space_id, ana, expense = ana_expense

    response = patch_expense(client, ana, space_id, expense["id"], {})

    assert response.status_code == 200
    assert response.json() == expense
    assert read(client, ana, space_id, expense["id"]) == expense


@pytest.mark.parametrize(
    "body",
    [
        {"amount": 20000.0},
        {"amount": 0},
        {"amount": None},
        {"spent_on": "2026-11-16"},  # Mañana con el reloj de mediados de noviembre.
        {"payment_type": "efectivo"},
    ],
)
def test_invalid_patch_is_rejected_and_changes_nothing(
    client: TestClient, ana_expense: AnaExpense, body: dict[str, object]
) -> None:
    space_id, ana, expense = ana_expense

    response = patch_expense(client, ana, space_id, expense["id"], body)

    assert response.status_code == 422
    assert read(client, ana, space_id, expense["id"]) == expense


def test_patching_a_category_of_another_space_is_rejected(
    client: TestClient, login: Login, ana_expense: AnaExpense
) -> None:
    # RF-5 también al editar.
    space_id, ana, expense = ana_expense
    bea = login("bea@example.com")
    foreign = first_category(client, bea, personal_space(client, bea))

    body = {"amount": 1, "category_id": foreign}
    response = patch_expense(client, ana, space_id, expense["id"], body)

    assert response.status_code == 422
    assert response.json()["detail"] == "La categoría no existe en este espacio."
    assert read(client, ana, space_id, expense["id"]) == expense


def test_patching_to_another_category_of_the_space(
    client: TestClient, ana_expense: AnaExpense
) -> None:
    space_id, ana, expense = ana_expense
    categories = client.get(f"/spaces/{space_id}/categories", headers=ana).json()
    other = categories[1]["id"]

    response = patch_expense(
        client, ana, space_id, expense["id"], {"category_id": other}
    )

    assert response.status_code == 200
    assert read(client, ana, space_id, expense["id"])["category_id"] == other


def test_patch_cannot_change_space_or_author(
    client: TestClient, engine: Engine, login: Login, ana_expense: AnaExpense
) -> None:
    # RF-14.
    space_id, ana, expense = ana_expense
    bea = login("bea@example.com")
    bea_id = client.get("/me", headers=bea).json()["id"]
    body = {"space_id": personal_space(client, bea), "created_by": bea_id}

    response = patch_expense(client, ana, space_id, expense["id"], body)

    assert response.status_code == 200
    with Session(engine) as db:
        stored = db.get_one(Expense, expense["id"])
        assert stored.space_id == space_id
        assert stored.created_by == expense["created_by"]


def test_patching_a_missing_expense_is_not_found(
    client: TestClient, ana_space: AnaSpace
) -> None:
    space_id, _, ana = ana_space

    response = patch_expense(client, ana, space_id, 1000, {"amount": 1})

    assert response.status_code == 404
    assert response.json()["detail"] == "Gasto no encontrado."


@pytest.mark.usefixtures("mid_november")
def test_a_member_edits_an_expense_registered_by_another(
    client: TestClient, shared_space: tuple[int, dict[str, str], dict[str, str]]
) -> None:
    # Criterio 3 (RF-15): Bea edita el gasto de Ana y el autor sigue siendo Ana.
    space_id, ana, bea = shared_space
    ana_id = client.get("/me", headers=ana).json()["id"]
    category_id = first_category(client, ana, space_id)
    expense = add_expense(client, ana, space_id, category_id, "2026-10-05")

    response = patch_expense(client, bea, space_id, expense["id"], {"amount": 9000})

    assert response.status_code == 200
    assert response.json()["amount"] == 9000
    assert response.json()["created_by"] == ana_id


# --- Borrar (T7) ---


def delete_expense(
    client: TestClient,
    headers: dict[str, str],
    space_id: int,
    expense_id: object,
    **params: str,
) -> object:
    return client.delete(
        f"/spaces/{space_id}/expenses/{expense_id}", params=params, headers=headers
    )


def test_deleting_with_confirmation_removes_the_expense(
    client: TestClient, ana_expense: AnaExpense
) -> None:
    # RF-16: borrado definitivo.
    space_id, ana, expense = ana_expense

    response = delete_expense(client, ana, space_id, expense["id"], confirm="true")

    assert response.status_code == 204
    read_back = client.get(f"/spaces/{space_id}/expenses/{expense['id']}", headers=ana)
    assert read_back.status_code == 404
    assert listed(client, ana, space_id, period="2026-10") == []


@pytest.mark.parametrize("params", [{}, {"confirm": "false"}])
def test_deleting_without_confirmation_is_rejected(
    client: TestClient, ana_expense: AnaExpense, params: dict[str, str]
) -> None:
    # RF-17.
    space_id, ana, expense = ana_expense

    response = delete_expense(client, ana, space_id, expense["id"], **params)

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Para borrar el gasto, confirma con confirm=true."
    )
    assert read(client, ana, space_id, expense["id"]) == expense


def test_deleting_an_expense_leaves_the_rest_of_the_space(
    client: TestClient, ana_space: AnaSpace, mid_november: None
) -> None:
    # RF-18.
    space_id, category_id, ana = ana_space
    categories = client.get(f"/spaces/{space_id}/categories", headers=ana).json()
    gone = add_expense(client, ana, space_id, category_id, "2026-10-05")
    kept = add_expense(client, ana, space_id, category_id, "2026-10-06")

    delete_expense(client, ana, space_id, gone["id"], confirm="true")

    assert listed(client, ana, space_id, period="2026-10") == [kept]
    assert client.get(f"/spaces/{space_id}/categories", headers=ana).json() == (
        categories
    )


def test_deleting_a_missing_expense_is_not_found(
    client: TestClient, ana_space: AnaSpace
) -> None:
    space_id, _, ana = ana_space

    response = delete_expense(client, ana, space_id, 1000, confirm="true")

    assert response.status_code == 404


@pytest.mark.usefixtures("mid_november")
def test_a_member_deletes_an_expense_registered_by_another(
    client: TestClient, shared_space: tuple[int, dict[str, str], dict[str, str]]
) -> None:
    # RF-15.
    space_id, ana, bea = shared_space
    category_id = first_category(client, ana, space_id)
    expense = add_expense(client, ana, space_id, category_id, "2026-10-05")

    response = delete_expense(client, bea, space_id, expense["id"], confirm="true")

    assert response.status_code == 204
    assert listed(client, ana, space_id, period="2026-10") == []


# --- Últimos registrados (spec 006, T1) ---


def register(
    client: TestClient,
    headers: dict[str, str],
    space_id: int,
    category_id: int,
    amount: int,
    spent_on: str = "2026-11-01",
) -> int:
    body = {
        "amount": amount,
        "payment_type": "debit",
        "category_id": category_id,
        "spent_on": spent_on,
    }
    response = client.post(f"/spaces/{space_id}/expenses", json=body, headers=headers)
    response.raise_for_status()
    return response.json()["id"]


def recent(
    client: TestClient, headers: dict[str, str], space_id: int, **params: object
) -> list[dict]:
    response = client.get(
        f"/spaces/{space_id}/expenses/recent", params=params, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_recent_orders_by_registration_not_by_date(
    client: TestClient,
    engine: Engine,
    shared_space: tuple[int, dict[str, str], dict[str, str]],
) -> None:
    # Criterio 1 de la 006 (RF-1): de cualquier mes y de cualquier miembro,
    # por momento de registro. El de septiembre tiene el `id` más bajo pero
    # se registró al final: el orden es por `created_at`, no por `id`.
    space_id, ana, bea = shared_space
    category_id = first_category(client, ana, space_id)
    september = register(client, ana, space_id, category_id, 1, "2026-09-10")
    others = [
        register(client, headers, space_id, category_id, amount)
        for amount, headers in zip(range(2, 8), [ana, bea] * 3, strict=True)
    ]
    with Session(engine) as db:
        expense = db.get_one(Expense, september)
        expense.created_at = datetime(2030, 1, 1, tzinfo=UTC)
        db.commit()

    ids = [expense["id"] for expense in recent(client, ana, space_id)]

    assert ids == [september, *reversed(others)][:5]


def test_recent_respects_the_limit(client: TestClient, ana_space: AnaSpace) -> None:
    space_id, category_id, ana = ana_space
    for amount in (1, 2, 3):
        register(client, ana, space_id, category_id, amount)

    assert [e["amount"] for e in recent(client, ana, space_id, limit=2)] == [3, 2]


@pytest.mark.parametrize("limit", [0, 21, "muchos"])
def test_recent_rejects_a_limit_out_of_range(
    client: TestClient, ana_space: AnaSpace, limit: object
) -> None:
    # RF-3.
    space_id, _, ana = ana_space

    response = client.get(
        f"/spaces/{space_id}/expenses/recent", params={"limit": limit}, headers=ana
    )

    assert response.status_code == 422


def test_recent_mine_only_returns_my_expenses(
    client: TestClient, shared_space: tuple[int, dict[str, str], dict[str, str]]
) -> None:
    # RF-2: lo que necesita `/deshacer`.
    space_id, ana, bea = shared_space
    category_id = first_category(client, ana, space_id)
    mine = register(client, ana, space_id, category_id, 1)
    register(client, bea, space_id, category_id, 2)

    assert [e["id"] for e in recent(client, ana, space_id, mine="true")] == [mine]
    assert len(recent(client, ana, space_id)) == 2


def test_recent_returns_the_expense_shape(
    client: TestClient, ana_space: AnaSpace
) -> None:
    space_id, category_id, ana = ana_space
    register(client, ana, space_id, category_id, 1)

    [expense] = recent(client, ana, space_id)

    assert set(expense) == set(ExpenseOut.model_fields)


def test_reading_one_expense_still_works_next_to_recent(
    client: TestClient, ana_space: AnaSpace
) -> None:
    # `/recent` va antes que `/{expense_id}` (plan 006): las dos conviven.
    space_id, category_id, ana = ana_space
    expense_id = register(client, ana, space_id, category_id, 1)

    response = client.get(f"/spaces/{space_id}/expenses/{expense_id}", headers=ana)

    assert response.status_code == 200
    assert response.json()["id"] == expense_id


# --- Categorías eliminadas (spec 008, RF-41, RF-42) ---


def deleted_category_setup(
    client: TestClient, login: Login
) -> tuple[dict[str, str], int, int, dict]:
    """Ana con un gasto en "Mascotas", y "Mascotas" ya eliminada."""
    ana = login("ana@example.com")
    space_id = client.get("/spaces", headers=ana).json()[0]["id"]
    mascotas = client.post(
        f"/spaces/{space_id}/categories", json={"name": "Mascotas"}, headers=ana
    ).json()["id"]
    expense = client.post(
        f"/spaces/{space_id}/expenses",
        json={"amount": 20000, "payment_type": "debit", "category_id": mascotas},
        headers=ana,
    ).json()
    client.delete(f"/spaces/{space_id}/categories/{mascotas}", headers=ana)
    return ana, space_id, mascotas, expense


def test_a_deleted_category_cannot_be_used_for_a_new_expense(
    client: TestClient, engine: Engine, login: Login
) -> None:
    ana, space_id, mascotas, _ = deleted_category_setup(client, login)

    response = client.post(
        f"/spaces/{space_id}/expenses",
        json={"amount": 5000, "payment_type": "debit", "category_id": mascotas},
        headers=ana,
    )

    assert response.status_code == 422
    assert "«Mascotas» fue eliminada" in response.json()["detail"]
    assert "créala otra vez con el mismo nombre" in response.json()["detail"]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Expense)) == 1


def test_an_expense_cannot_be_moved_to_a_deleted_category(
    client: TestClient, login: Login
) -> None:
    ana, space_id, mascotas, _ = deleted_category_setup(client, login)
    comida = client.post(
        f"/spaces/{space_id}/expenses",
        json={"amount": 5000, "payment_type": "debit", "category_id": 2},
        headers=ana,
    ).json()

    response = client.patch(
        f"/spaces/{space_id}/expenses/{comida['id']}",
        json={"category_id": mascotas},
        headers=ana,
    )

    assert response.status_code == 422
    assert "fue eliminada" in response.json()["detail"]


def test_an_expense_in_a_deleted_category_can_still_be_edited(
    client: TestClient, login: Login
) -> None:
    # RF-42: editar otro campo no exige cambiarle la categoría.
    ana, space_id, mascotas, expense = deleted_category_setup(client, login)

    response = client.patch(
        f"/spaces/{space_id}/expenses/{expense['id']}",
        json={"amount": 25000},
        headers=ana,
    )

    assert response.status_code == 200
    assert response.json()["amount"] == 25000
    assert response.json()["category_id"] == mascotas


# --- Gastos con rubro (spec 008, RF-17 a RF-22) ---

EXACTLY_ONE = (
    "Indica el rubro del gasto o, si no estaba planeado, su categoría, pero no los dos."
)


@pytest.mark.parametrize(
    "body",
    [
        {"amount": 20000, "payment_type": "debit"},
        {
            "amount": 20000,
            "payment_type": "debit",
            "category_id": 1,
            "budget_item_id": 2,
        },
    ],
)
def test_expense_in_needs_exactly_a_budget_item_or_a_category(body: dict) -> None:
    # RF-17, criterio 4.
    with pytest.raises(ValidationError) as exc:
        ExpenseIn.model_validate(body)
    assert EXACTLY_ONE in error_message(exc)


@pytest.mark.parametrize("budget_item_id", ["2", True, 2.0])
def test_budget_item_id_must_be_an_integer(budget_item_id: object) -> None:
    with pytest.raises(ValidationError):
        ExpenseIn.model_validate(
            {"amount": 1, "payment_type": "debit", "budget_item_id": budget_item_id}
        )


def test_a_patch_accepts_null_to_remove_the_budget_item() -> None:
    patch = ExpensePatch.model_validate({"budget_item_id": None})
    assert patch.model_dump(exclude_unset=True) == {"budget_item_id": None}


class Plan:
    """Espacio personal de Ana con rubros de octubre y septiembre de 2026."""

    def __init__(self, client: TestClient, headers: dict[str, str]) -> None:
        self.client, self.headers = client, headers
        self.space_id = personal_space(client, headers)
        listed = client.get(f"/spaces/{self.space_id}/categories", headers=headers)
        self.categories = {c["name"]: c["id"] for c in listed.json()}
        self.mercado = self.item("Mercado", "Comida", "2026-10")
        self.arriendo = self.item("Arriendo", "Hogar", "2026-10")
        self.mercado_septiembre = self.item("Mercado", "Comida", "2026-09")

    def item(self, name: str, category: str, period: str) -> dict:
        body = {
            "period": period,
            "name": name,
            "category_id": self.categories[category],
            "amount": 800000,
        }
        return self.client.post(
            f"/spaces/{self.space_id}/budget-items", json=body, headers=self.headers
        ).json()

    def register(self, **fields: object):
        body = {"amount": 20000, "payment_type": "debit", **fields}
        return self.client.post(
            f"/spaces/{self.space_id}/expenses", json=body, headers=self.headers
        )

    def patch(self, expense_id: int, body: dict):
        return self.client.patch(
            f"/spaces/{self.space_id}/expenses/{expense_id}",
            json=body,
            headers=self.headers,
        )


@pytest.fixture
def plan(client: TestClient, login: Login, fixed_clock: None) -> Plan:
    return Plan(client, login("ana@example.com"))


def test_a_planned_expense_takes_the_category_of_its_item(plan: Plan) -> None:
    # RF-20, decisión 13: se escribe el rubro y la categoría sale de él.
    response = plan.register(budget_item_id=plan.mercado["id"], spent_on="2026-10-15")

    assert response.status_code == 201
    assert response.json()["budget_item_id"] == plan.mercado["id"]
    assert response.json()["category_id"] == plan.categories["Comida"]


def test_an_unplanned_expense_has_no_item(plan: Plan) -> None:
    response = plan.register(category_id=plan.categories["Salud"])

    assert response.status_code == 201
    assert response.json()["budget_item_id"] is None
    assert response.json()["category_id"] == plan.categories["Salud"]


@pytest.mark.parametrize(
    "fields",
    [{}, {"category_id": 1, "budget_item_id": 1}],
)
def test_both_or_neither_is_rejected(plan: Plan, engine: Engine, fields: dict) -> None:
    response = plan.register(**fields)

    assert response.status_code == 422
    assert EXACTLY_ONE in response.text
    assert count_expenses(engine) == 0


def test_an_item_of_another_month_is_rejected(plan: Plan, engine: Engine) -> None:
    # RF-19, criterio 4: un gasto del 3 de octubre no va a un rubro de
    # septiembre.
    response = plan.register(
        budget_item_id=plan.mercado_septiembre["id"], spent_on="2026-10-03"
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "El rubro «Mercado» es de 2026-09 y el gasto es de 2026-10. Elige un rubro "
        "de 2026-10 o regístralo como no planeado."
    )
    assert count_expenses(engine) == 0


def test_an_item_of_another_space_is_rejected(
    client: TestClient, login: Login, plan: Plan, engine: Engine
) -> None:
    # RF-18: aunque quien llama sea miembro de los dos, igual que inexistente.
    casa = client.post("/spaces", json={"name": "Casa"}, headers=plan.headers).json()
    hogar_casa = client.get(
        f"/spaces/{casa['id']}/categories", headers=plan.headers
    ).json()[0]["id"]
    foreign = client.post(
        f"/spaces/{casa['id']}/budget-items",
        json={"period": "2026-10", "name": "X", "category_id": hogar_casa, "amount": 1},
        headers=plan.headers,
    ).json()["id"]

    for item_id in (foreign, 999_999):
        response = plan.register(budget_item_id=item_id)
        assert response.status_code == 422
        assert response.json()["detail"] == "El rubro no existe en este espacio."
    assert count_expenses(engine) == 0


def test_an_item_whose_category_was_deleted_still_takes_expenses(
    plan: Plan,
) -> None:
    # RF-42, decisión 17.
    plan.client.delete(
        f"/spaces/{plan.space_id}/categories/{plan.categories['Comida']}",
        headers=plan.headers,
    )

    response = plan.register(budget_item_id=plan.mercado["id"])

    assert response.status_code == 201
    assert response.json()["category_id"] == plan.categories["Comida"]


def test_moving_a_planned_expense_to_another_month_is_rejected(plan: Plan) -> None:
    # RF-19, criterio 4.
    expense = plan.register(
        budget_item_id=plan.mercado["id"], spent_on="2026-10-15"
    ).json()

    response = plan.patch(expense["id"], {"spent_on": "2026-09-30"})

    assert response.status_code == 422
    assert "es de 2026-10 y el gasto es de 2026-09" in response.json()["detail"]


def test_moving_month_and_item_together_is_accepted(plan: Plan) -> None:
    expense = plan.register(
        budget_item_id=plan.mercado["id"], spent_on="2026-10-15"
    ).json()

    response = plan.patch(
        expense["id"],
        {"spent_on": "2026-09-30", "budget_item_id": plan.mercado_septiembre["id"]},
    )

    assert response.status_code == 200
    assert response.json()["budget_item_id"] == plan.mercado_septiembre["id"]


def test_linking_to_another_item_changes_the_category(plan: Plan) -> None:
    # RF-21.
    expense = plan.register(category_id=plan.categories["Salud"]).json()

    response = plan.patch(expense["id"], {"budget_item_id": plan.arriendo["id"]})

    assert response.status_code == 200
    assert response.json()["budget_item_id"] == plan.arriendo["id"]
    assert response.json()["category_id"] == plan.categories["Hogar"]


def test_removing_the_item_keeps_or_changes_the_category(plan: Plan) -> None:
    # RF-21: sin categoría, queda la que tenía; con categoría, la enviada.
    kept = plan.register(budget_item_id=plan.mercado["id"]).json()
    moved = plan.register(budget_item_id=plan.mercado["id"]).json()

    kept_response = plan.patch(kept["id"], {"budget_item_id": None})
    moved_response = plan.patch(
        moved["id"], {"budget_item_id": None, "category_id": plan.categories["Ocio"]}
    )

    assert kept_response.json()["budget_item_id"] is None
    assert kept_response.json()["category_id"] == plan.categories["Comida"]
    assert moved_response.json()["budget_item_id"] is None
    assert moved_response.json()["category_id"] == plan.categories["Ocio"]


def test_the_category_of_a_planned_expense_cannot_change_alone(plan: Plan) -> None:
    # RF-21.
    expense = plan.register(budget_item_id=plan.mercado["id"]).json()

    response = plan.patch(expense["id"], {"category_id": plan.categories["Ocio"]})

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "El gasto está en el rubro «Mercado» y usa su categoría. Para cambiarla, "
        "quítale el rubro."
    )


def test_a_patch_with_an_item_and_a_category_is_rejected(plan: Plan) -> None:
    expense = plan.register(category_id=plan.categories["Salud"]).json()

    response = plan.patch(
        expense["id"],
        {"budget_item_id": plan.mercado["id"], "category_id": plan.categories["Ocio"]},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == EXACTLY_ONE


def test_listing_and_recent_bring_the_item(plan: Plan) -> None:
    # RF-20, RF-22.
    expense = plan.register(budget_item_id=plan.mercado["id"]).json()
    base = f"/spaces/{plan.space_id}/expenses"

    listed = plan.client.get(f"{base}?period=2026-10", headers=plan.headers).json()
    recent = plan.client.get(f"{base}/recent", headers=plan.headers).json()

    assert listed == [expense]
    assert recent == [expense]
    assert expense["budget_item_id"] == plan.mercado["id"]


# --- Compras con tarjeta (spec 009, T4) ---

CARD_REQUIRED = "Un gasto a crédito necesita la tarjeta con la que se pagó."
# Spec 010: las reglas de la 009 valen para las deudas.
NO_ITEM_ON_CARD = (
    "Una deuda no lleva rubro: cuenta en Deudas el mes en que se paga la "
    "tarjeta. Indica su categoría."
)
DESCRIPTION_REQUIRED = (
    "Una deuda necesita una descripción: es el nombre con el que sus cuotas "
    "salen en Deudas."
)
INSTALLMENTS_ARE_DEBT = "Una compra a varias cuotas siempre es deuda."
DEBIT_WITHOUT_CARD = "Un gasto a débito no lleva tarjeta ni cuotas."
INSTALLMENTS_RANGE = "Las cuotas deben ser un número entero de 1 a 48."

# 1 de diciembre de 2026 a mediodía en Bogotá: las compras de noviembre ya
# no son futuras.
DECEMBER_1 = datetime(2026, 12, 1, 17, 0, tzinfo=UTC)


class Cards(Plan):
    """Espacio de Ana con la Visa (corte 25, pago 10, 1,90 %), la Master
    (corte 15, pago 30) y el rubro "Mercado" de noviembre."""

    def __init__(self, client: TestClient, headers: dict[str, str]) -> None:
        super().__init__(client, headers)
        self.visa = self.card("Visa", 25, 10)
        self.master = self.card("Master", 15, 30)
        self.mercado_noviembre = self.item("Mercado", "Comida", "2026-11")

    def card(self, name: str, cutoff_day: int, due_day: int) -> dict:
        body = {
            "name": name,
            "cutoff_day": cutoff_day,
            "due_day": due_day,
            "monthly_rate": 1.9,
        }
        return self.client.post(
            f"/spaces/{self.space_id}/cards", json=body, headers=self.headers
        ).json()

    def purchase(self, **fields: object):
        """La "Compra TV" del 12 de noviembre con la Visa, salvo otro dato."""
        body = {
            "payment_type": "credit",
            "card_id": self.visa["id"],
            "category_id": self.categories["Hogar"],
            "description": "Compra TV",
            "amount": 1200000,
            "spent_on": "2026-11-12",
            # Deuda, como la 009 trataba toda compra con tarjeta (spec 010).
            "is_debt": True,
            **fields,
        }
        return self.client.post(
            f"/spaces/{self.space_id}/expenses",
            json={k: v for k, v in body.items() if v is not None},
            headers=self.headers,
        )


@pytest.fixture
def cards(client: TestClient, login: Login, monkeypatch: pytest.MonkeyPatch) -> Cards:
    monkeypatch.setattr(dates, "now", lambda: DECEMBER_1)
    return Cards(client, login("ana@example.com"))


def test_a_card_purchase_is_registered_with_its_payment_month(cards: Cards) -> None:
    # RF-9, RF-13, RF-18: corte 25 y pago 10, compra del 12 de noviembre →
    # primera cuota en diciembre.
    response = cards.purchase(installments=6)

    assert response.status_code == 201
    body = response.json()
    assert body["card_id"] == cards.visa["id"]
    assert body["installments"] == 6
    assert body["first_due_period"] == "2026-12"
    assert body["budget_item_id"] is None
    assert body["category_id"] == cards.categories["Hogar"]
    assert body["description"] == "Compra TV"


def test_a_card_purchase_has_one_installment_by_default(cards: Cards) -> None:
    body = cards.purchase(spent_on="2026-11-26").json()

    assert body["installments"] == 1
    # Después del corte del 25: entra al corte de diciembre y se paga en enero.
    assert body["first_due_period"] == "2027-01"


def test_a_debit_expense_has_no_card_fields(cards: Cards) -> None:
    body = cards.register(category_id=cards.categories["Salud"]).json()

    assert (body["card_id"], body["installments"], body["first_due_period"]) == (
        None,
        None,
        None,
    )


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"card_id": None}, CARD_REQUIRED),
        ({"description": None}, DESCRIPTION_REQUIRED),
        ({"description": "   "}, DESCRIPTION_REQUIRED),
        ({"category_id": None}, "Una deuda necesita su categoría."),
        ({"installments": 0}, INSTALLMENTS_RANGE),
        ({"installments": 49}, INSTALLMENTS_RANGE),
        ({"installments": "3"}, INSTALLMENTS_RANGE),
        ({"installments": 3.0}, INSTALLMENTS_RANGE),
        ({"installments": True}, INSTALLMENTS_RANGE),
        ({"payment_type": "debit"}, DEBIT_WITHOUT_CARD),
    ],
)
def test_an_invalid_card_purchase_is_rejected(
    cards: Cards, engine: Engine, fields: dict, message: str
) -> None:
    # Criterio 6 (RF-9 a RF-11).
    before = count_expenses(engine)

    response = cards.purchase(**fields)

    assert response.status_code == 422
    assert message in response.text
    assert count_expenses(engine) == before


def test_a_card_purchase_with_a_budget_item_is_rejected(
    cards: Cards, engine: Engine
) -> None:
    response = cards.purchase(budget_item_id=cards.mercado_noviembre["id"])

    assert response.status_code == 422
    assert NO_ITEM_ON_CARD in response.text
    assert count_expenses(engine) == 0


def test_a_debit_expense_with_installments_is_rejected(cards: Cards) -> None:
    response = cards.register(category_id=cards.categories["Salud"], installments=1)

    assert response.status_code == 422
    assert DEBIT_WITHOUT_CARD in response.text


def test_an_archived_card_cannot_take_new_purchases(
    cards: Cards, engine: Engine
) -> None:
    cards.client.delete(
        f"/spaces/{cards.space_id}/cards/{cards.visa['id']}", headers=cards.headers
    )

    response = cards.purchase()

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "La tarjeta «Visa» fue eliminada. Para usarla de nuevo, créala otra vez "
        "con el mismo nombre."
    )
    assert count_expenses(engine) == 0


@pytest.mark.parametrize("other_space", [True, False])
def test_a_card_of_another_space_or_missing_is_rejected(
    cards: Cards, engine: Engine, other_space: bool
) -> None:
    # RF-12, RF-43: Ana es miembro de los dos espacios y aun así la tarjeta del
    # otro no sirve; responde igual que una inexistente.
    if other_space:
        viajes = cards.client.post(
            "/spaces", json={"name": "Viajes"}, headers=cards.headers
        ).json()
        body = {"name": "Amex", "cutoff_day": 1, "due_day": 15}
        card_id = cards.client.post(
            f"/spaces/{viajes['id']}/cards", json=body, headers=cards.headers
        ).json()["id"]
    else:
        card_id = 999

    response = cards.purchase(card_id=card_id)

    assert response.status_code == 422
    assert response.json()["detail"] == "La tarjeta no existe en este espacio."
    assert count_expenses(engine) == 0


def test_the_description_of_a_card_purchase_cannot_be_removed(cards: Cards) -> None:
    purchase = cards.purchase().json()

    for description in (None, ""):
        response = cards.patch(purchase["id"], {"description": description})

        assert response.status_code == 422
        assert response.json()["detail"] == DESCRIPTION_REQUIRED
    assert read(cards.client, cards.headers, cards.space_id, purchase["id"]) == purchase


def test_editing_the_purchase_recalculates_its_payment_month(cards: Cards) -> None:
    # Criterio 8, primera parte (RF-5, RF-14, decisión 13).
    purchase = cards.purchase().json()
    cards.client.patch(
        f"/spaces/{cards.space_id}/cards/{cards.visa['id']}",
        json={"cutoff_day": 5},
        headers=cards.headers,
    )

    # Cambiar los días de la tarjeta no mueve la compra, ni editar su
    # descripción o su categoría.
    renamed = cards.patch(
        purchase["id"],
        {"description": "TV sala", "category_id": cards.categories["Ocio"]},
    ).json()
    assert renamed["first_due_period"] == "2026-12"

    # Cambiar la fecha recalcula con el corte nuevo: corte 5 y pago 10 de
    # noviembre. Con el corte viejo habría seguido en diciembre.
    moved = cards.patch(purchase["id"], {"spent_on": "2026-11-03"}).json()
    assert moved["first_due_period"] == "2026-11"


def test_changing_card_or_installments_recalculates_the_payment_month(
    cards: Cards,
) -> None:
    purchase = cards.purchase().json()

    # Master: corte 15 y pago 30 → se paga el 30 de noviembre.
    to_master = cards.patch(purchase["id"], {"card_id": cards.master["id"]}).json()
    assert to_master["first_due_period"] == "2026-11"

    more = cards.patch(purchase["id"], {"installments": 12}).json()
    assert (more["installments"], more["first_due_period"]) == (12, "2026-11")


def test_patching_to_an_archived_card_is_rejected(cards: Cards) -> None:
    purchase = cards.purchase().json()
    cards.client.delete(
        f"/spaces/{cards.space_id}/cards/{cards.master['id']}", headers=cards.headers
    )

    response = cards.patch(purchase["id"], {"card_id": cards.master["id"]})

    assert response.status_code == 422
    assert "fue eliminada" in response.json()["detail"]


def test_debit_to_credit_needs_a_card_and_drops_the_item(cards: Cards) -> None:
    # RF-15.
    planned = cards.register(
        budget_item_id=cards.mercado_noviembre["id"],
        spent_on="2026-11-12",
        description="Éxito",
    ).json()

    without_card = cards.patch(planned["id"], {"payment_type": "credit"})
    keeps_item = cards.patch(
        planned["id"],
        {"payment_type": "credit", "card_id": cards.visa["id"], "is_debt": True},
    )
    assert without_card.json()["detail"] == CARD_REQUIRED
    assert keeps_item.json()["detail"] == NO_ITEM_ON_CARD

    converted = cards.patch(
        planned["id"],
        {
            "payment_type": "credit",
            "card_id": cards.visa["id"],
            "budget_item_id": None,
            "is_debt": True,
        },
    )

    assert converted.status_code == 200
    body = converted.json()
    assert body["budget_item_id"] is None
    assert body["category_id"] == cards.categories["Comida"]
    assert (body["installments"], body["first_due_period"]) == (1, "2026-12")


def test_debit_to_credit_needs_a_description(cards: Cards) -> None:
    unplanned = cards.register(
        category_id=cards.categories["Ocio"], spent_on="2026-11-12"
    ).json()
    to_credit = {
        "payment_type": "credit",
        "card_id": cards.visa["id"],
        "is_debt": True,
    }

    response = cards.patch(unplanned["id"], to_credit)
    assert response.json()["detail"] == DESCRIPTION_REQUIRED

    response = cards.patch(unplanned["id"], {**to_credit, "description": "Cine"})
    assert response.status_code == 200
    assert response.json()["first_due_period"] == "2026-12"


def test_credit_to_debit_drops_the_card(cards: Cards) -> None:
    purchase = cards.purchase(installments=6).json()

    body = cards.patch(purchase["id"], {"payment_type": "debit"}).json()

    assert (body["card_id"], body["installments"], body["first_due_period"]) == (
        None,
        None,
        None,
    )
    assert body["budget_item_id"] is None
    assert body["category_id"] == cards.categories["Hogar"]


def test_credit_to_debit_can_go_into_an_item(cards: Cards) -> None:
    purchase = cards.purchase().json()

    body = cards.patch(
        purchase["id"],
        {"payment_type": "debit", "budget_item_id": cards.mercado_noviembre["id"]},
    ).json()

    assert body["budget_item_id"] == cards.mercado_noviembre["id"]
    assert body["category_id"] == cards.categories["Comida"]
    assert body["card_id"] is None


def test_a_debit_expense_cannot_get_a_card_while_staying_debit(cards: Cards) -> None:
    unplanned = cards.register(category_id=cards.categories["Ocio"]).json()

    for body in ({"card_id": cards.visa["id"]}, {"installments": 3}):
        response = cards.patch(unplanned["id"], body)
        assert response.status_code == 422
        assert response.json()["detail"] == DEBIT_WITHOUT_CARD


def legacy_credit_expense(engine: Engine, cards: Cards, **fields: object) -> int:
    """Gasto a crédito sin tarjeta, como los registrados antes de la 009."""
    with Session(engine) as db:
        expense = Expense(
            **{
                "space_id": cards.space_id,
                "category_id": cards.categories["Comida"],
                "created_by": 1,
                "amount": 90000,
                "payment_type": "credit",
                "spent_on": date(2026, 11, 2),
                **fields,
            }
        )
        db.add(expense)
        db.commit()
        return expense.id


def test_a_legacy_credit_expense_is_edited_without_a_card(
    cards: Cards, engine: Engine
) -> None:
    # Criterio 5, parte de gastos (RF-17).
    expense_id = legacy_credit_expense(engine, cards)

    edited = cards.patch(
        expense_id,
        {"amount": 95000, "budget_item_id": cards.mercado_noviembre["id"]},
    )

    assert edited.status_code == 200
    body = edited.json()
    assert body["payment_type"] == "credit"
    assert body["budget_item_id"] == cards.mercado_noviembre["id"]
    assert body["card_id"] is None


def test_a_legacy_credit_expense_becomes_a_card_purchase(
    cards: Cards, engine: Engine
) -> None:
    expense_id = legacy_credit_expense(
        engine,
        cards,
        budget_item_id=cards.mercado_noviembre["id"],
        description="Mercado viejo",
    )

    keeps_item = cards.patch(expense_id, {"card_id": cards.visa["id"], "is_debt": True})
    assert keeps_item.json()["detail"] == NO_ITEM_ON_CARD

    converted = cards.patch(
        expense_id,
        {"card_id": cards.visa["id"], "budget_item_id": None, "is_debt": True},
    ).json()
    assert converted["card_id"] == cards.visa["id"]
    assert (converted["installments"], converted["first_due_period"]) == (
        1,
        "2026-12",
    )


def test_a_debit_expense_cannot_become_credit_without_a_card(cards: Cards) -> None:
    # Solo un gasto que ya era a crédito sin tarjeta sigue sin ella (RF-17).
    unplanned = cards.register(category_id=cards.categories["Ocio"]).json()

    response = cards.patch(unplanned["id"], {"payment_type": "credit"})

    assert response.json()["detail"] == CARD_REQUIRED


def test_the_list_uses_the_purchase_date(cards: Cards) -> None:
    # RF-18: el listado es el registro; el dinero lo cuenta el resumen.
    purchase = cards.purchase(installments=6).json()
    base = f"/spaces/{cards.space_id}/expenses"

    november = cards.client.get(f"{base}?period=2026-11", headers=cards.headers)
    december = cards.client.get(f"{base}?period=2026-12", headers=cards.headers)

    assert november.json() == [purchase]
    assert december.json() == []


# --- Gasto del mes o deuda (spec 010, T2) ---


def month_purchase(cards: Cards, **fields: object):
    """El "Mercado" de 200.000 del 5 de noviembre con la Visa, a 1 cuota, en
    el rubro "Mercado" de noviembre y sin decir si es deuda."""
    body = {
        "payment_type": "credit",
        "card_id": cards.visa["id"],
        "budget_item_id": cards.mercado_noviembre["id"],
        "amount": 200000,
        "spent_on": "2026-11-05",
        **fields,
    }
    return cards.client.post(
        f"/spaces/{cards.space_id}/expenses",
        json={k: v for k, v in body.items() if v is not None},
        headers=cards.headers,
    )


def test_a_card_purchase_in_the_plan_is_a_month_expense(cards: Cards) -> None:
    # Criterio 1 (RF-1, RF-2, RF-4): a 1 cuota y sin decirlo, es del mes.
    response = month_purchase(cards)

    assert response.status_code == 201
    body = response.json()
    assert body["is_debt"] is False
    assert body["budget_item_id"] == cards.mercado_noviembre["id"]
    assert body["category_id"] == cards.categories["Comida"]
    assert body["description"] is None
    assert (body["installments"], body["first_due_period"]) == (1, "2026-12")


def test_a_month_expense_without_item_takes_a_category(cards: Cards) -> None:
    response = month_purchase(
        cards, budget_item_id=None, category_id=cards.categories["Ocio"]
    )

    assert response.status_code == 201
    body = response.json()
    assert (body["is_debt"], body["budget_item_id"], body["description"]) == (
        False,
        None,
        None,
    )


def test_a_purchase_in_several_installments_is_a_debt(cards: Cards) -> None:
    body = cards.purchase(installments=6, is_debt=None).json()

    assert body["is_debt"] is True


def test_a_debit_expense_has_no_debt_flag(cards: Cards) -> None:
    body = cards.register(category_id=cards.categories["Salud"]).json()

    assert body["is_debt"] is None


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"installments": 6, "is_debt": False}, INSTALLMENTS_ARE_DEBT),
        ({"is_debt": True, "description": "Mercado"}, NO_ITEM_ON_CARD),
        (
            {"is_debt": True, "budget_item_id": None, "category_id": 2},
            DESCRIPTION_REQUIRED,
        ),
        ({"category_id": 2}, EXACTLY_ONE),
        ({"budget_item_id": None}, EXACTLY_ONE),
        ({"is_debt": "true"}, "valid boolean"),
    ],
)
def test_an_invalid_month_expense_or_debt_is_rejected(
    cards: Cards, engine: Engine, fields: dict, message: str
) -> None:
    # Criterio 4 (RF-1 a RF-3).
    response = month_purchase(cards, **fields)

    assert response.status_code == 422
    assert message in response.text
    assert count_expenses(engine) == 0


def test_a_month_expense_needs_an_item_of_its_month(
    cards: Cards, engine: Engine
) -> None:
    # El rubro "Mercado" de octubre no sirve para una compra de noviembre.
    response = month_purchase(cards, budget_item_id=cards.mercado["id"])

    assert response.status_code == 422
    assert "es de 2026-10 y el gasto es de 2026-11" in response.json()["detail"]
    assert count_expenses(engine) == 0


def test_a_debit_expense_with_a_debt_flag_is_rejected(cards: Cards) -> None:
    response = cards.register(category_id=cards.categories["Salud"], is_debt=False)

    assert response.status_code == 422
    assert DEBIT_WITHOUT_CARD in response.text


def test_a_month_expense_becomes_a_debt_without_its_item(cards: Cards) -> None:
    # Criterio 5 (RF-5).
    mercado = month_purchase(cards).json()

    keeps_item = cards.patch(mercado["id"], {"is_debt": True})
    assert keeps_item.status_code == 422
    assert keeps_item.json()["detail"] == NO_ITEM_ON_CARD

    no_description = cards.patch(
        mercado["id"], {"is_debt": True, "budget_item_id": None}
    )
    assert no_description.json()["detail"] == DESCRIPTION_REQUIRED

    debt = cards.patch(
        mercado["id"],
        {"is_debt": True, "budget_item_id": None, "description": "Mercado Éxito"},
    )
    assert debt.status_code == 200
    body = debt.json()
    assert (body["is_debt"], body["budget_item_id"]) == (True, None)
    assert body["category_id"] == cards.categories["Comida"]


def test_several_installments_make_a_month_expense_a_debt(cards: Cards) -> None:
    cine = month_purchase(
        cards,
        budget_item_id=None,
        category_id=cards.categories["Ocio"],
        description="Cine",
    ).json()

    body = cards.patch(cine["id"], {"installments": 3}).json()

    assert (body["installments"], body["is_debt"]) == (3, True)


def test_several_installments_with_an_item_need_to_drop_it(cards: Cards) -> None:
    mercado = month_purchase(cards).json()

    response = cards.patch(mercado["id"], {"installments": 3})

    assert response.json()["detail"] == NO_ITEM_ON_CARD


def test_a_debt_in_several_installments_cannot_be_a_month_expense(
    cards: Cards,
) -> None:
    tv = cards.purchase(installments=6).json()

    response = cards.patch(tv["id"], {"is_debt": False})

    assert response.status_code == 422
    assert response.json()["detail"] == INSTALLMENTS_ARE_DEBT


def test_a_one_installment_debt_becomes_a_month_expense(cards: Cards) -> None:
    zapatos = cards.purchase(
        description="Zapatos", amount=150000, spent_on="2026-11-20"
    ).json()
    assert zapatos["is_debt"] is True

    body = cards.patch(
        zapatos["id"],
        {"is_debt": False, "budget_item_id": cards.mercado_noviembre["id"]},
    ).json()

    assert body["is_debt"] is False
    assert body["budget_item_id"] == cards.mercado_noviembre["id"]
    assert body["category_id"] == cards.categories["Comida"]


def test_debit_to_credit_keeps_the_item_as_a_month_expense(cards: Cards) -> None:
    planned = cards.register(
        budget_item_id=cards.mercado_noviembre["id"], spent_on="2026-11-12"
    ).json()

    body = cards.patch(
        planned["id"], {"payment_type": "credit", "card_id": cards.visa["id"]}
    ).json()

    assert (body["is_debt"], body["budget_item_id"]) == (
        False,
        cards.mercado_noviembre["id"],
    )
    assert body["first_due_period"] == "2026-12"
