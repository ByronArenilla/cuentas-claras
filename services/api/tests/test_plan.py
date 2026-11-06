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
        "debts": 0,
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


# --- Copiar el plan (RF-13 a RF-16) ---


def copy(space: Space, period: str | None = None, headers: dict | None = None):
    body = {"period": period} if period else {}
    return space.client.post(
        f"/spaces/{space.id}/plan/copy",
        json=body,
        headers=space.headers if headers is None else headers,
    )


def plan_of(space: Space, period: str) -> dict:
    """Rubros e ingresos del mes, sin ids, tal como los muestra el resumen."""
    summary = space.summary(period).json()
    return {
        "incomes": [(row["name"], row["amount"]) for row in summary["incomes"]],
        "budget_items": [
            (row["name"], row["category_id"], row["planned"])
            for row in summary["budget_items"]
        ],
    }


@pytest.fixture
def november(ana: Space) -> dict:
    """Plan de noviembre de Ana, con un gasto en Mercado."""
    ana.income("2026-11", "Salario", 5_000_000)
    ana.income("2026-11", "Bonificación", 300_000)
    arriendo = ana.item("2026-11", "Arriendo", "Hogar", 1_500_000)
    mercado = ana.item("2026-11", "Mercado", "Comida", 800_000)
    return {"arriendo": arriendo, "mercado": mercado}


def test_copying_creates_the_same_plan_in_the_next_month(
    ana: Space, november: dict, engine
) -> None:
    # Criterio 3.
    before = ana.summary("2026-11").json()

    response = copy(ana, "2026-12")

    assert response.status_code == 201
    body = response.json()
    assert body["skipped"] == []
    assert body["summary"] == ana.summary("2026-12").json()
    assert plan_of(ana, "2026-12") == plan_of(ana, "2026-11")
    assert plan_of(ana, "2026-12") == {
        "incomes": [("Salario", 5_000_000), ("Bonificación", 300_000)],
        "budget_items": [
            ("Arriendo", ana.categories["Hogar"], 1_500_000),
            ("Mercado", ana.categories["Comida"], 800_000),
        ],
    }
    # Son filas nuevas, y noviembre no cambia.
    new_ids = {row["id"] for row in body["summary"]["budget_items"]}
    assert new_ids.isdisjoint({november["arriendo"]["id"], november["mercado"]["id"]})
    assert ana.summary("2026-11").json() == before


def test_copying_does_not_touch_the_expenses_of_the_source(ana: Space) -> None:
    # RF-16: el gasto de octubre sigue en su rubro de octubre, y noviembre
    # empieza sin gastado.
    mercado = ana.item("2026-10", "Mercado", "Comida", 800_000)
    expense = ana.spend(412_000, "2026-10-03", budget_item_id=mercado["id"])
    before = ana.summary("2026-10").json()

    response = copy(ana, "2026-11")
    listed = ana.client.get(
        f"/spaces/{ana.id}/expenses", params={"period": "2026-10"}, headers=ana.headers
    ).json()

    assert response.status_code == 201
    assert listed == [expense]
    assert expense["budget_item_id"] == mercado["id"]
    assert ana.summary("2026-10").json() == before
    assert response.json()["summary"]["budget_items"][0]["spent"] == 0
    assert response.json()["summary"]["total"]["spent"] == 0


@pytest.mark.parametrize("what", ["item", "income"])
def test_a_month_with_any_plan_is_not_copied_over(ana: Space, november: dict, what):
    # RF-14: ni mezcla ni reemplaza.
    if what == "item":
        ana.item("2026-12", "Regalos", "Ocio", 200_000)
    else:
        ana.income("2026-12", "Prima", 2_500_000)
    before = plan_of(ana, "2026-12")

    response = copy(ana, "2026-12")

    assert response.status_code == 409
    assert response.json()["detail"] == "2026-12 ya tiene un plan; no se copió nada."
    assert plan_of(ana, "2026-12") == before


def test_copying_twice_is_rejected(ana: Space, november: dict) -> None:
    copy(ana, "2026-12")

    response = copy(ana, "2026-12")

    assert response.status_code == 409
    assert len(plan_of(ana, "2026-12")["budget_items"]) == 2


def test_an_empty_previous_month_is_rejected(ana: Space, november: dict) -> None:
    # RF-15: enero se copiaría de diciembre, que está vacío.
    response = copy(ana, "2027-01")

    assert response.status_code == 409
    assert response.json()["detail"] == "2026-12 no tiene un plan para copiar."
    assert plan_of(ana, "2027-01") == {"incomes": [], "budget_items": []}


def test_items_of_deleted_categories_are_skipped_and_reported(
    ana: Space, november: dict
) -> None:
    # RF-13, decisión 15.
    ana.client.delete(
        f"/spaces/{ana.id}/categories/{ana.categories['Hogar']}", headers=ana.headers
    )

    response = copy(ana, "2026-12")

    assert response.status_code == 201
    assert response.json()["skipped"] == [{"name": "Arriendo", "category": "Hogar"}]
    assert plan_of(ana, "2026-12")["budget_items"] == [
        ("Mercado", ana.categories["Comida"], 800_000)
    ]
    assert len(plan_of(ana, "2026-12")["incomes"]) == 2


def test_only_items_of_deleted_categories_is_nothing_to_copy(ana: Space) -> None:
    # RF-15: si todo se omite y no hay ingresos, no hay nada que copiar.
    ana.item("2026-11", "Arriendo", "Hogar", 1_500_000)
    ana.client.delete(
        f"/spaces/{ana.id}/categories/{ana.categories['Hogar']}", headers=ana.headers
    )

    response = copy(ana, "2026-12")

    assert response.status_code == 409
    assert response.json()["detail"] == "2026-11 no tiene un plan para copiar."
    assert plan_of(ana, "2026-12") == {"incomes": [], "budget_items": []}


def test_without_period_it_copies_into_the_current_month(ana: Space) -> None:
    # Criterio 6: el 31 de octubre a las 20:00 en Bogotá copia septiembre a
    # octubre.
    ana.income("2026-09", "Salario", 5_000_000)

    response = copy(ana)

    assert response.status_code == 201
    assert response.json()["summary"]["period"] == "2026-10"
    assert plan_of(ana, "2026-10")["incomes"] == [("Salario", 5_000_000)]


def test_a_copy_that_collides_leaves_nothing_half_done(
    ana: Space, november: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    # RF-14: si otra copia llegó a la vez, la comprobación previa no la ve y
    # el índice único frena el INSERT. Se simula que la comprobación no vio
    # nada.
    from app import plan

    copy(ana, "2026-12")
    before = plan_of(ana, "2026-12")
    monkeypatch.setattr(plan, "has_plan", lambda *_args: False)

    response = copy(ana, "2026-12")

    assert response.status_code == 409
    assert response.json()["detail"] == "2026-12 ya tiene un plan; no se copió nada."
    assert plan_of(ana, "2026-12") == before


def test_deleting_restoring_and_copying_again(ana: Space, november: dict) -> None:
    # Criterio 13 de punta a punta: con "Hogar" eliminada su rubro no se copia;
    # al restaurarla, se copia de nuevo.
    hogar = ana.categories["Hogar"]
    ana.client.delete(f"/spaces/{ana.id}/categories/{hogar}", headers=ana.headers)
    december = copy(ana, "2026-12").json()
    restored = ana.client.post(
        f"/spaces/{ana.id}/categories", json={"name": "hogar"}, headers=ana.headers
    )
    ana.item("2026-12", "Arriendo", "Hogar", 1_500_000)

    january = copy(ana, "2027-01").json()

    assert december["skipped"] == [{"name": "Arriendo", "category": "Hogar"}]
    assert restored.json() == {"id": hogar, "name": "Hogar"}
    assert january["skipped"] == []
    assert ("Arriendo", hogar, 1_500_000) in plan_of(ana, "2027-01")["budget_items"]


def test_copying_without_session_is_rejected(ana: Space, november: dict) -> None:
    assert copy(ana, "2026-12", headers={}).status_code == 401
    assert plan_of(ana, "2026-12") == {"incomes": [], "budget_items": []}
