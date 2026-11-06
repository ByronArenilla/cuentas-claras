"""Plan de cuotas de una compra con tarjeta y sus abonos (spec 009, RF-21 a
RF-30)."""

from collections.abc import Callable
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app import dates
from app.models import Expense

Login = Callable[..., dict[str, str]]

# 1 de diciembre de 2026 a mediodía en Bogotá.
DECEMBER_1 = datetime(2026, 12, 1, 17, 0, tzinfo=UTC)

TV_INSTALLMENTS = [
    # (número, mes, capital, interés, saldo después)
    (1, "2026-12", 200000, 22800, 1000000),
    (2, "2027-01", 200000, 19000, 800000),
    (3, "2027-02", 200000, 15200, 600000),
    (4, "2027-03", 200000, 11400, 400000),
    (5, "2027-04", 200000, 7600, 200000),
    (6, "2027-05", 200000, 3800, 0),
]


class Space:
    """Espacio de Ana con la Visa (corte 25, pago 10, 1,90 %) y la "Compra
    TV" de 1.200.000 a 6 cuotas del 12 de noviembre."""

    def __init__(self, client: TestClient, headers: dict[str, str]) -> None:
        self.client, self.headers = client, headers
        self.id = client.get("/spaces", headers=headers).json()[0]["id"]
        self.base = f"/spaces/{self.id}"
        listed = client.get(f"{self.base}/categories", headers=headers).json()
        self.categories = {c["name"]: c["id"] for c in listed}
        self.visa = self.post(
            "/cards",
            {"name": "Visa", "cutoff_day": 25, "due_day": 10, "monthly_rate": 1.9},
        ).json()
        self.tv = self.purchase().json()

    def post(self, path: str, body: dict) -> Response:
        return self.client.post(f"{self.base}{path}", json=body, headers=self.headers)

    def get(self, path: str) -> Response:
        return self.client.get(f"{self.base}{path}", headers=self.headers)

    def purchase(self, **fields: object) -> Response:
        body = {
            "payment_type": "credit",
            "card_id": self.visa["id"],
            "category_id": self.categories["Hogar"],
            "description": "Compra TV",
            "amount": 1200000,
            "installments": 6,
            "spent_on": "2026-11-12",
            **fields,
        }
        return self.post("/expenses", body)

    def schedule(self, expense_id: int | None = None) -> Response:
        return self.get(f"/expenses/{expense_id or self.tv['id']}/installments")


@pytest.fixture
def space(client: TestClient, login: Login, monkeypatch: pytest.MonkeyPatch) -> Space:
    monkeypatch.setattr(dates, "now", lambda: DECEMBER_1)
    return Space(client, login("ana@example.com"))


def installments(schedule: dict) -> list[tuple]:
    return [
        (
            row["number"],
            row["period"],
            row["capital"],
            row["interest"],
            row["balance_after"],
        )
        for row in schedule["installments"]
    ]


# --- Plan de cuotas (RF-21) ---


def test_the_schedule_of_a_purchase(space: Space) -> None:
    # Criterio 2 por HTTP.
    response = space.schedule()

    assert response.status_code == 200
    body = response.json()
    assert body["expense_id"] == space.tv["id"]
    assert body["card_id"] == space.visa["id"]
    assert installments(body) == TV_INSTALLMENTS
    assert body["installments"][0] == {
        "number": 1,
        "count": 6,
        "period": "2026-12",
        "capital": 200000,
        "interest": 22800,
        "amount": 222800,
        "balance_after": 1000000,
    }
    assert body["prepayments"] == []


NO_INSTALLMENTS = "Este gasto no es una compra con tarjeta; no tiene cuotas."


def test_a_debit_expense_has_no_schedule(space: Space) -> None:
    debit = space.post(
        "/expenses",
        {"amount": 20000, "payment_type": "debit", "category_id": 1},
    ).json()

    response = space.schedule(debit["id"])

    assert response.status_code == 404
    assert response.json()["detail"] == NO_INSTALLMENTS


def test_a_legacy_credit_expense_has_no_schedule(space: Space, engine: Engine) -> None:
    with Session(engine) as db:
        legacy = Expense(
            space_id=space.id,
            category_id=space.categories["Comida"],
            created_by=1,
            amount=90000,
            payment_type="credit",
            spent_on=date(2026, 11, 2),
        )
        db.add(legacy)
        db.commit()
        legacy_id = legacy.id

    response = space.schedule(legacy_id)

    assert response.status_code == 404
    assert response.json()["detail"] == NO_INSTALLMENTS


def test_a_missing_expense_has_no_schedule(space: Space) -> None:
    response = space.schedule(999)

    assert response.status_code == 404
    assert response.json()["detail"] == "Gasto no encontrado."


def test_changing_the_rate_changes_the_interest(space: Space) -> None:
    # Decisión 14: la estimación usa la tasa actual de la tarjeta.
    space.client.patch(
        f"{space.base}/cards/{space.visa['id']}",
        json={"monthly_rate": 2},
        headers=space.headers,
    )

    body = space.schedule().json()

    assert [row["interest"] for row in body["installments"]] == [
        24000,
        20000,
        16000,
        12000,
        8000,
        4000,
    ]


def test_a_card_without_rate_has_no_interest(space: Space) -> None:
    space.client.patch(
        f"{space.base}/cards/{space.visa['id']}",
        json={"monthly_rate": None},
        headers=space.headers,
    )

    body = space.schedule().json()

    assert all(row["interest"] == 0 for row in body["installments"])


# --- Abonos (RF-22 a RF-28) ---


def prepay(space: Space, expense_id: int | None = None, **fields: object) -> Response:
    body = {"amount": 400000, "period": "2026-12", "reduces": "term", **fields}
    return space.post(f"/expenses/{expense_id or space.tv['id']}/prepayments", body)


def amounts(schedule: dict) -> list[tuple[str, int]]:
    return [(row["period"], row["amount"]) for row in schedule["installments"]]


def test_a_prepayment_reducing_the_term(space: Space) -> None:
    # Criterio 3 por HTTP.
    response = prepay(space)

    assert response.status_code == 201
    body = response.json()
    assert body["prepayment"] == {
        "id": body["prepayment"]["id"],
        "expense_id": space.tv["id"],
        "period": "2026-12",
        "amount": 400000,
        "reduces": "term",
    }
    assert amounts(body["schedule"]) == [
        ("2026-12", 222800),
        ("2027-01", 211400),
        ("2027-02", 207600),
        ("2027-03", 203800),
    ]
    assert body["schedule"]["prepayments"] == [body["prepayment"]]
    assert space.schedule().json() == body["schedule"]


def test_a_prepayment_reducing_the_installment(space: Space) -> None:
    body = prepay(space, reduces="installment").json()

    assert amounts(body["schedule"]) == [
        ("2026-12", 222800),
        ("2027-01", 131400),
        ("2027-02", 129120),
        ("2027-03", 126840),
        ("2027-04", 124560),
        ("2027-05", 122280),
    ]


def test_a_prepayment_of_the_whole_balance_cancels_the_purchase(space: Space) -> None:
    body = prepay(space, amount=1000000).json()

    assert amounts(body["schedule"]) == [("2026-12", 222800)]


def test_a_prepayment_above_the_balance_is_rejected(space: Space) -> None:
    response = prepay(space, amount=1000001)

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "El saldo de la compra después de la cuota de 2026-12 es 1.000.000; el "
        "abono no puede pasar de ahí."
    )
    assert space.schedule().json()["prepayments"] == []


@pytest.mark.parametrize("period", ["2026-11", "2027-05", "2027-06"])
def test_a_prepayment_in_a_month_without_balance_is_rejected(
    space: Space, period: str
) -> None:
    # Antes de la primera cuota, en la última (sin saldo después) o después.
    response = prepay(space, period=period, amount=1)

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "La compra tiene cuotas de 2026-12 a 2027-05 y queda saldo después de "
        "las de 2026-12 a 2027-04; elige uno de esos meses."
    )


def test_a_second_prepayment_in_the_same_month_is_rejected(space: Space) -> None:
    prepay(space)

    response = prepay(space, amount=1)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "La compra ya tiene un abono en 2026-12; un abono nuevo debe ser de un "
        "mes posterior."
    )
    assert len(space.schedule().json()["prepayments"]) == 1


def test_a_prepayment_before_the_last_one_is_rejected(space: Space) -> None:
    prepay(space, period="2027-02", amount=100000)

    response = prepay(space, period="2027-01", amount=1)

    assert response.status_code == 409
    assert "2027-02" in response.json()["detail"]
    assert len(space.schedule().json()["prepayments"]) == 1


def test_a_later_prepayment_is_accepted(space: Space) -> None:
    prepay(space, reduces="installment")

    response = prepay(space, period="2027-02", amount=200000, reduces="term")

    assert response.status_code == 201
    assert [row["capital"] for row in response.json()["schedule"]["installments"]] == [
        200000,
        120000,
        120000,
        120000,
        40000,
    ]


def test_a_prepayment_without_period_is_of_the_current_month(space: Space) -> None:
    response = space.post(
        f"/expenses/{space.tv['id']}/prepayments",
        {"amount": 1000, "reduces": "term"},
    )

    assert response.json()["prepayment"]["period"] == "2026-12"


@pytest.mark.parametrize(
    "fields",
    [
        {"amount": 0},
        {"amount": 1.5},
        {"amount": "1000"},
        {"reduces": "plazo"},
        {"reduces": None},
        {"period": "2026-13"},
    ],
)
def test_an_invalid_prepayment_is_rejected(space: Space, fields: dict) -> None:
    response = prepay(space, **fields)

    assert response.status_code == 422
    assert space.schedule().json()["prepayments"] == []


def test_only_card_purchases_take_prepayments(space: Space) -> None:
    debit = space.post(
        "/expenses",
        {"amount": 20000, "payment_type": "debit", "category_id": 1},
    ).json()

    response = prepay(space, debit["id"])

    assert response.status_code == 422
    assert response.json()["detail"] == "Solo se abona a una compra con tarjeta."


def test_a_purchase_of_an_archived_card_takes_prepayments(space: Space) -> None:
    space.client.delete(f"{space.base}/cards/{space.visa['id']}", headers=space.headers)

    assert prepay(space).status_code == 201


def test_a_prepayment_to_a_missing_expense_is_not_found(space: Space) -> None:
    assert prepay(space, 999).status_code == 404


def delete_prepayment(space: Space, prepayment_id: int, **params: str) -> Response:
    return space.client.delete(
        f"{space.base}/expenses/{space.tv['id']}/prepayments/{prepayment_id}",
        params=params,
        headers=space.headers,
    )


def test_deleting_a_prepayment_needs_confirmation(space: Space) -> None:
    prepayment = prepay(space).json()["prepayment"]

    response = delete_prepayment(space, prepayment["id"])

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Para borrar el abono, confirma con confirm=true."
    )
    assert len(space.schedule().json()["prepayments"]) == 1


def test_deleting_a_prepayment_restores_the_installments(space: Space) -> None:
    prepayment = prepay(space).json()["prepayment"]

    response = delete_prepayment(space, prepayment["id"], confirm="true")

    assert response.status_code == 204
    schedule = space.schedule().json()
    assert installments(schedule) == TV_INSTALLMENTS
    assert schedule["prepayments"] == []


def test_deleting_a_missing_prepayment_is_not_found(space: Space) -> None:
    response = delete_prepayment(space, 999, confirm="true")

    assert response.status_code == 404
    assert response.json()["detail"] == "Abono no encontrado."


def test_a_prepayment_of_another_purchase_is_not_found(space: Space) -> None:
    other = space.purchase(description="Celular").json()
    prepayment = prepay(space, other["id"]).json()["prepayment"]

    # La ruta es de la TV, el abono es del celular.
    response = delete_prepayment(space, prepayment["id"], confirm="true")

    assert response.status_code == 404


def test_a_prepayment_never_changes_the_purchase(space: Space) -> None:
    # RF-28.
    prepay(space)

    assert space.get(f"/expenses/{space.tv['id']}").json() == space.tv


# --- Compras con abonos (RF-16) ---

HAS_PREPAYMENTS = (
    "La compra tiene abonos: solo puedes cambiar su descripción y su categoría. "
    "Para cambiar lo demás o borrarla, borra primero sus abonos."
)


def patch_tv(space: Space, body: dict) -> Response:
    return space.client.patch(
        f"{space.base}/expenses/{space.tv['id']}", json=body, headers=space.headers
    )


def test_a_purchase_with_prepayments_changes_description_and_category(
    space: Space,
) -> None:
    # Criterio 9.
    prepay(space)

    response = patch_tv(
        space, {"description": "TV sala", "category_id": space.categories["Ocio"]}
    )

    assert response.status_code == 200
    assert response.json()["description"] == "TV sala"


@pytest.mark.parametrize(
    "body",
    [
        {"amount": 1000000},
        {"spent_on": "2026-11-13"},
        {"installments": 12},
        {"payment_type": "debit"},
        {"card_id": 1},
    ],
)
def test_a_purchase_with_prepayments_cannot_change_the_rest(
    space: Space, body: dict
) -> None:
    prepay(space)

    response = patch_tv(space, body)

    assert response.status_code == 409
    assert response.json()["detail"] == HAS_PREPAYMENTS
    assert space.get(f"/expenses/{space.tv['id']}").json() == space.tv


def test_a_purchase_with_prepayments_is_deleted_after_its_prepayments(
    space: Space,
) -> None:
    prepayment = prepay(space).json()["prepayment"]
    url = f"{space.base}/expenses/{space.tv['id']}"

    refused = space.client.delete(
        url, params={"confirm": "true"}, headers=space.headers
    )
    assert refused.status_code == 409
    assert refused.json()["detail"] == HAS_PREPAYMENTS

    delete_prepayment(space, prepayment["id"], confirm="true")
    deleted = space.client.delete(
        url, params={"confirm": "true"}, headers=space.headers
    )
    assert deleted.status_code == 204
