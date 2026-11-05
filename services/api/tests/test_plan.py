"""Resumen del mes y copia del plan por HTTP (spec 008, RF-13 a RF-16 y
RF-23 a RF-27)."""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app import dates
from app.schemas import PERIOD_FORMAT_MESSAGE

Login = Callable[..., dict[str, str]]
SharedSpace = tuple[int, dict[str, str], dict[str, str]]

# 2026-10-31 a las 20:00 en Bogotá (UTC-5): en UTC ya es 1 de noviembre.
NOW = datetime(2026, 11, 1, 1, 0, tzinfo=UTC)


@pytest.fixture
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dates, "now", lambda: NOW)


class Space:
    """Un espacio con atajos para planear, registrar y pedir el resumen."""

    def __init__(self, client: TestClient, headers: dict[str, str], space_id: int):
        self.client, self.headers, self.id = client, headers, space_id
        listed = client.get(f"/spaces/{space_id}/categories", headers=headers)
        self.categories = {c["name"]: c["id"] for c in listed.json()}

    def item(self, period: str, name: str, category: str, amount: int) -> dict:
        body = {
            "period": period,
            "name": name,
            "category_id": self.categories[category],
            "amount": amount,
        }
        response = self.client.post(
            f"/spaces/{self.id}/budget-items", json=body, headers=self.headers
        )
        assert response.status_code == 201, response.text
        return response.json()

    def income(self, period: str, name: str, amount: int) -> dict:
        body = {"period": period, "name": name, "amount": amount}
        response = self.client.post(
            f"/spaces/{self.id}/incomes", json=body, headers=self.headers
        )
        assert response.status_code == 201, response.text
        return response.json()

    def spend(self, amount: int, day: str, **fields: object) -> dict:
        body = {"amount": amount, "payment_type": "debit", "spent_on": day, **fields}
        response = self.client.post(
            f"/spaces/{self.id}/expenses", json=body, headers=self.headers
        )
        assert response.status_code == 201, response.text
        return response.json()

    def summary(self, period: str | None = None, headers: dict | None = None):
        params = {"period": period} if period else {}
        return self.client.get(
            f"/spaces/{self.id}/summary",
            params=params,
            headers=self.headers if headers is None else headers,
        )


@pytest.fixture
def ana(client: TestClient, login: Login, fixed_clock: None) -> Space:
    headers = login("ana@example.com")
    space_id = client.get("/spaces", headers=headers).json()[0]["id"]
    return Space(client, headers, space_id)


# --- Resumen (RF-23 a RF-26) ---


def test_the_summary_of_october_end_to_end(ana: Space) -> None:
    # Criterio 1 por HTTP: plan, gastos planeados y no planeados, y totales.
    ana.income("2026-10", "Salario", 5_000_000)
    mercado = ana.item("2026-10", "Mercado", "Comida", 800_000)
    ana.spend(812_000, "2026-10-03", budget_item_id=mercado["id"])
    ana.spend(38_000, "2026-10-10", category_id=ana.categories["Transporte"])

    response = ana.summary("2026-10")

    assert response.status_code == 200
    summary = response.json()
    assert summary["budget_items"] == [
        {
            "id": mercado["id"],
            "name": "Mercado",
            "category_id": ana.categories["Comida"],
            "planned": 800_000,
            "spent": 812_000,
            "remaining": -12_000,
        }
    ]
    assert [row["name"] for row in summary["categories"]] == list(ana.categories)
    assert summary["total"] == {
        "income": 5_000_000,
        "planned": 800_000,
        "spent_planned": 812_000,
        "spent_unplanned": 38_000,
        "spent": 850_000,
        "unassigned": 4_200_000,
        "balance": 4_150_000,
    }


def test_without_period_the_summary_is_the_current_month(ana: Space) -> None:
    # Criterio 6: el 31 de octubre a las 20:00 en Bogotá sigue siendo octubre.
    ana.income("2026-10", "Salario", 5_000_000)

    summary = ana.summary().json()

    assert summary["period"] == "2026-10"
    assert summary["total"]["income"] == 5_000_000


@pytest.mark.parametrize("period", ["2026-13", "octubre"])
def test_an_invalid_period_is_rejected(ana: Space, period: str) -> None:
    response = ana.summary(period)

    assert response.status_code == 422
    assert response.json()["detail"] == PERIOD_FORMAT_MESSAGE


def test_members_see_the_same_summary(
    client: TestClient, shared_space: SharedSpace
) -> None:
    space_id, ana_headers, bea_headers = shared_space
    casa = Space(client, ana_headers, space_id)
    casa.item("2026-10", "Mercado", "Comida", 800_000)

    assert (
        casa.summary("2026-10").json()
        == casa.summary("2026-10", headers=bea_headers).json()
    )


def test_the_summary_without_session_is_rejected(ana: Space) -> None:
    assert ana.summary("2026-10", headers={}).status_code == 401


# --- La ruta de la 004 ya no existe (RF-27, criterio 11) ---


def test_the_budget_route_of_the_004_is_gone(ana: Space) -> None:
    response = ana.client.put(
        f"/spaces/{ana.id}/budgets/{ana.categories['Comida']}",
        json={"period": "2026-10", "amount": 400_000},
        headers=ana.headers,
    )

    assert response.status_code == 404
