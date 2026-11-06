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
