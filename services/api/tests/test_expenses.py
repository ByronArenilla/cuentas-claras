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

    patch_expense(client, ana, space_id, expense["id"], {"payment_type": "credit"})

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
