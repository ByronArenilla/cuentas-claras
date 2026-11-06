"""Rutas de tarjetas (spec 009, RF-1 a RF-8)."""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app import dates
from app.models import Card, CardStatement, Expense

Login = Callable[..., dict[str, str]]

# 1 de diciembre de 2026 a mediodía en Bogotá.
DECEMBER_1 = datetime(2026, 12, 1, 17, 0, tzinfo=UTC)

VISA = {"name": "Visa", "cutoff_day": 25, "due_day": 10, "monthly_rate": 1.9}


def personal_space(client: TestClient, headers: dict[str, str]) -> int:
    return client.get("/spaces", headers=headers).json()[0]["id"]


def create_card(
    client: TestClient, headers: dict[str, str], space_id: int, **fields: object
) -> Response:
    return client.post(
        f"/spaces/{space_id}/cards", json={**VISA, **fields}, headers=headers
    )


def cards_in(engine: Engine) -> int:
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(Card))


def stored_card(engine: Engine, card_id: int) -> Card:
    with Session(engine) as db:
        return db.get_one(Card, card_id)


@pytest.fixture
def ana(client: TestClient, login: Login) -> tuple[dict[str, str], int]:
    headers = login("ana@example.com")
    return headers, personal_space(client, headers)


# --- Crear y validar (RF-1 a RF-3) ---


def test_creating_a_card_returns_it(client: TestClient, engine: Engine, ana) -> None:
    headers, space_id = ana

    response = create_card(client, headers, space_id, name="  Visa  ")

    assert response.status_code == 201
    body = response.json()
    assert body == {
        "id": body["id"],
        "name": "Visa",
        "cutoff_day": 25,
        "due_day": 10,
        "monthly_rate": 1.9,
        "deleted": False,
    }
    # 1,90 % se guarda como 190 puntos básicos: exacto, sin `float`.
    assert stored_card(engine, body["id"]).monthly_rate_bp == 190


def test_rate_is_kept_exact(client: TestClient, engine: Engine, ana) -> None:
    headers, space_id = ana

    body = create_card(client, headers, space_id, monthly_rate=1.89).json()

    assert body["monthly_rate"] == 1.89
    assert stored_card(engine, body["id"]).monthly_rate_bp == 189


def test_rate_is_optional(client: TestClient, ana) -> None:
    headers, space_id = ana
    fields = {key: value for key, value in VISA.items() if key != "monthly_rate"}

    response = client.post(f"/spaces/{space_id}/cards", json=fields, headers=headers)

    assert response.status_code == 201
    assert response.json()["monthly_rate"] is None


@pytest.mark.parametrize(
    "fields",
    [
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 51},
        {"cutoff_day": 0},
        {"cutoff_day": 32},
        {"cutoff_day": "5"},
        {"cutoff_day": 5.0},
        {"due_day": 0},
        {"due_day": 32},
        {"due_day": True},
        {"monthly_rate": 0},
        {"monthly_rate": 10.01},
        {"monthly_rate": 1.895},
        {"monthly_rate": -1},
        {"monthly_rate": "1.89"},
        {"monthly_rate": True},
    ],
)
def test_invalid_card_is_rejected(
    client: TestClient, engine: Engine, ana, fields: dict[str, object]
) -> None:
    headers, space_id = ana

    response = create_card(client, headers, space_id, **fields)

    assert response.status_code == 422
    assert cards_in(engine) == 0


def test_rate_limits_are_accepted(client: TestClient, ana) -> None:
    headers, space_id = ana

    low = create_card(client, headers, space_id, name="Baja", monthly_rate=0.01)
    high = create_card(client, headers, space_id, name="Alta", monthly_rate=10)

    assert (low.status_code, high.status_code) == (201, 201)
    assert high.json()["monthly_rate"] == 10


def test_equivalent_name_is_rejected_naming_the_existing_card(
    client: TestClient, engine: Engine, ana
) -> None:
    headers, space_id = ana
    create_card(client, headers, space_id)

    response = create_card(client, headers, space_id, name="visa")

    assert response.status_code == 409
    assert response.json()["detail"] == "Ya existe la tarjeta «Visa»."
    assert cards_in(engine) == 1


# --- Listar (RF-4) ---


def test_listing_returns_active_cards_in_creation_order(
    client: TestClient, ana
) -> None:
    headers, space_id = ana
    for name in ("Visa", "Master", "Amex"):
        create_card(client, headers, space_id, name=name)
    amex = client.get(f"/spaces/{space_id}/cards", headers=headers).json()[2]
    client.delete(f"/spaces/{space_id}/cards/{amex['id']}", headers=headers)

    listed = client.get(f"/spaces/{space_id}/cards", headers=headers).json()

    assert [card["name"] for card in listed] == ["Visa", "Master"]


# --- Editar (RF-5) ---


def test_editing_changes_only_what_is_sent(client: TestClient, ana) -> None:
    headers, space_id = ana
    card = create_card(client, headers, space_id).json()

    response = client.patch(
        f"/spaces/{space_id}/cards/{card['id']}",
        json={"cutoff_day": 5},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == {**card, "cutoff_day": 5}


def test_null_rate_removes_it(client: TestClient, engine: Engine, ana) -> None:
    headers, space_id = ana
    card = create_card(client, headers, space_id).json()

    response = client.patch(
        f"/spaces/{space_id}/cards/{card['id']}",
        json={"monthly_rate": None},
        headers=headers,
    )

    assert response.json()["monthly_rate"] is None
    assert stored_card(engine, card["id"]).monthly_rate_bp is None


@pytest.mark.parametrize("field", ["name", "cutoff_day", "due_day"])
def test_null_is_rejected_in_other_fields(client: TestClient, ana, field: str) -> None:
    headers, space_id = ana
    card = create_card(client, headers, space_id).json()

    response = client.patch(
        f"/spaces/{space_id}/cards/{card['id']}", json={field: None}, headers=headers
    )

    assert response.status_code == 422


def test_renaming_to_an_equivalent_name_is_rejected(client: TestClient, ana) -> None:
    headers, space_id = ana
    create_card(client, headers, space_id, name="Master")
    card = create_card(client, headers, space_id).json()

    response = client.patch(
        f"/spaces/{space_id}/cards/{card['id']}",
        json={"name": "MASTER"},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Ya existe la tarjeta «Master»."


def test_renaming_a_card_to_its_own_name_works(client: TestClient, ana) -> None:
    headers, space_id = ana
    card = create_card(client, headers, space_id).json()

    response = client.patch(
        f"/spaces/{space_id}/cards/{card['id']}",
        json={"name": "VISA"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "VISA"


def test_an_archived_card_can_be_edited(client: TestClient, ana) -> None:
    headers, space_id = ana
    card = create_card(client, headers, space_id).json()
    client.delete(f"/spaces/{space_id}/cards/{card['id']}", headers=headers)

    response = client.patch(
        f"/spaces/{space_id}/cards/{card['id']}",
        json={"monthly_rate": 2},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["monthly_rate"] == 2
    assert response.json()["deleted"] is True


# --- Eliminar y restaurar (RF-6, RF-7) ---


def test_deleting_archives_the_card_with_a_notice(
    client: TestClient, engine: Engine, ana
) -> None:
    headers, space_id = ana
    card = create_card(client, headers, space_id).json()

    response = client.delete(f"/spaces/{space_id}/cards/{card['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "id": card["id"],
        "name": "Visa",
        "message": "Eliminaste «Visa». Sus cuotas pendientes siguen llegando a "
        "Deudas. Para volver a usarla en compras nuevas, créala de nuevo con el "
        "mismo nombre.",
    }
    assert client.get(f"/spaces/{space_id}/cards", headers=headers).json() == []
    assert stored_card(engine, card["id"]).deleted_at is not None


def test_creating_an_archived_name_restores_the_original_card(
    client: TestClient, engine: Engine, ana
) -> None:
    headers, space_id = ana
    card = create_card(client, headers, space_id).json()
    client.delete(f"/spaces/{space_id}/cards/{card['id']}", headers=headers)

    # Otros días y otra tasa: se restaura como era (decisión 24).
    response = create_card(
        client, headers, space_id, name="VISA", cutoff_day=1, due_day=2, monthly_rate=3
    )

    assert response.status_code == 200
    assert response.json() == card
    assert cards_in(engine) == 1
    listed = client.get(f"/spaces/{space_id}/cards", headers=headers).json()
    assert listed == [card]


# --- No encontrada (RF-8) ---


def test_missing_card_is_not_found(client: TestClient, ana) -> None:
    headers, space_id = ana
    url = f"/spaces/{space_id}/cards/999"

    for response in (
        client.patch(url, json={"cutoff_day": 5}, headers=headers),
        client.delete(url, headers=headers),
    ):
        assert response.status_code == 404
        assert response.json()["detail"] == "Tarjeta no encontrada."


def test_deleting_an_archived_card_is_not_found(client: TestClient, ana) -> None:
    headers, space_id = ana
    card = create_card(client, headers, space_id).json()
    url = f"/spaces/{space_id}/cards/{card['id']}"
    client.delete(url, headers=headers)

    assert client.delete(url, headers=headers).status_code == 404


def test_a_card_of_another_space_is_not_found(
    client: TestClient, login: Login, ana
) -> None:
    headers, space_id = ana
    card = create_card(client, headers, space_id).json()
    # Ana es miembro de los dos espacios: la tarjeta sigue sin verse desde el
    # otro (RF-8).
    other = client.post("/spaces", json={"name": "Viajes"}, headers=headers).json()
    url = f"/spaces/{other['id']}/cards/{card['id']}"

    assert client.patch(url, json={"cutoff_day": 5}, headers=headers).status_code == 404
    assert client.delete(url, headers=headers).status_code == 404


def test_cards_need_a_session(client: TestClient, ana) -> None:
    _, space_id = ana

    assert client.get(f"/spaces/{space_id}/cards").status_code == 401
    assert client.post(f"/spaces/{space_id}/cards", json=VISA).status_code == 401


# --- Valor real del extracto (RF-31 a RF-33) ---


@pytest.fixture
def visa(client: TestClient, ana) -> tuple[dict[str, str], int, dict]:
    headers, space_id = ana
    return headers, space_id, create_card(client, headers, space_id).json()


def statement_url(space_id: int, card_id: int, period: str = "2026-12") -> str:
    return f"/spaces/{space_id}/cards/{card_id}/statements/{period}"


def statements_in(engine: Engine) -> list[tuple]:
    with Session(engine) as db:
        return [
            (row.card_id, row.period_start.isoformat(), row.amount)
            for row in db.scalars(select(CardStatement).order_by(CardStatement.id))
        ]


def test_writing_a_statement_returns_it(
    client: TestClient, engine: Engine, visa
) -> None:
    headers, space_id, card = visa

    response = client.put(
        statement_url(space_id, card["id"]), json={"amount": 431500}, headers=headers
    )

    assert response.status_code == 200
    assert response.json() == {
        "card_id": card["id"],
        "period": "2026-12",
        "amount": 431500,
    }
    assert statements_in(engine) == [(card["id"], "2026-12-01", 431500)]


def test_writing_it_again_replaces_it(client: TestClient, engine: Engine, visa) -> None:
    headers, space_id, card = visa
    url = statement_url(space_id, card["id"])
    client.put(url, json={"amount": 431500}, headers=headers)

    response = client.put(url, json={"amount": 0}, headers=headers)

    assert response.json()["amount"] == 0
    assert statements_in(engine) == [(card["id"], "2026-12-01", 0)]


@pytest.mark.parametrize(
    "amount", [-1, 1.5, 431500.0, "431500", True, None, 1_000_000_000_001]
)
def test_an_invalid_statement_is_rejected(
    client: TestClient, engine: Engine, visa, amount: object
) -> None:
    headers, space_id, card = visa

    response = client.put(
        statement_url(space_id, card["id"]), json={"amount": amount}, headers=headers
    )

    assert response.status_code == 422
    assert statements_in(engine) == []


def test_a_statement_of_one_trillion_is_accepted(client: TestClient, visa) -> None:
    headers, space_id, card = visa

    response = client.put(
        statement_url(space_id, card["id"]),
        json={"amount": 1_000_000_000_000},
        headers=headers,
    )

    assert response.status_code == 200


@pytest.mark.parametrize("period", ["2026-13", "2026-1", "diciembre"])
def test_a_statement_of_an_invalid_period_is_rejected(
    client: TestClient, visa, period: str
) -> None:
    headers, space_id, card = visa

    response = client.put(
        statement_url(space_id, card["id"], period), json={"amount": 1}, headers=headers
    )

    assert response.status_code == 422
    assert "AAAA-MM" in response.json()["detail"]


def test_an_archived_card_takes_statements(client: TestClient, visa) -> None:
    headers, space_id, card = visa
    client.delete(f"/spaces/{space_id}/cards/{card['id']}", headers=headers)

    response = client.put(
        statement_url(space_id, card["id"]), json={"amount": 15000}, headers=headers
    )

    assert response.status_code == 200


def test_removing_a_statement(client: TestClient, engine: Engine, visa) -> None:
    headers, space_id, card = visa
    url = statement_url(space_id, card["id"])
    client.put(url, json={"amount": 431500}, headers=headers)

    response = client.delete(url, headers=headers)

    assert response.status_code == 204
    assert statements_in(engine) == []
    again = client.delete(url, headers=headers)
    assert again.status_code == 404
    assert again.json()["detail"] == (
        "2026-12 no tiene valor del extracto para esta tarjeta."
    )


def test_statements_of_a_missing_card_are_not_found(client: TestClient, ana) -> None:
    headers, space_id = ana
    url = statement_url(space_id, 999)

    assert client.put(url, json={"amount": 1}, headers=headers).status_code == 404
    assert client.delete(url, headers=headers).status_code == 404


def test_copying_the_plan_does_not_copy_statements(
    client: TestClient, engine: Engine, visa
) -> None:
    # RF-33: cada extracto es de su mes.
    headers, space_id, card = visa
    categories = client.get(f"/spaces/{space_id}/categories", headers=headers).json()
    client.post(
        f"/spaces/{space_id}/budget-items",
        json={
            "period": "2026-11",
            "name": "Arriendo",
            "category_id": categories[0]["id"],
            "amount": 1500000,
        },
        headers=headers,
    )
    client.put(
        statement_url(space_id, card["id"], "2026-11"),
        json={"amount": 431500},
        headers=headers,
    )

    copied = client.post(
        f"/spaces/{space_id}/plan/copy", json={"period": "2026-12"}, headers=headers
    )

    assert copied.status_code == 201
    assert statements_in(engine) == [(card["id"], "2026-11-01", 431500)]


# --- Pagar todo (RF-29, RF-30) ---


class Payoff:
    """Visa (corte 25, pago 10, 1,90 %) con la "Compra TV" (12 de noviembre,
    6 cuotas), el "Mercado" (5 de noviembre, 1 cuota) y unos "Zapatos" (30 de
    noviembre, 1 cuota, después del corte)."""

    def __init__(self, client: TestClient, headers: dict[str, str]) -> None:
        self.client, self.headers = client, headers
        self.space_id = personal_space(client, headers)
        self.base = f"/spaces/{self.space_id}"
        self.card = create_card(client, headers, self.space_id).json()
        self.tv = self.purchase("Compra TV", 1200000, "2026-11-12", 6)
        self.mercado = self.purchase("Mercado", 200000, "2026-11-05", 1)
        self.zapatos = self.purchase("Zapatos", 150000, "2026-11-30", 1)

    def purchase(self, description: str, amount: int, day: str, count: int) -> dict:
        categories = self.client.get(
            f"{self.base}/categories", headers=self.headers
        ).json()
        body = {
            "payment_type": "credit",
            "card_id": self.card["id"],
            "category_id": categories[0]["id"],
            "description": description,
            "amount": amount,
            "spent_on": day,
            "installments": count,
            # Deuda, como la 009 trataba toda compra con tarjeta (spec 010).
            "is_debt": True,
        }
        response = self.client.post(
            f"{self.base}/expenses", json=body, headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def pay_off(self, card_id: int | None = None, **body: object) -> Response:
        return self.client.post(
            f"{self.base}/cards/{card_id or self.card['id']}/payoff",
            json=body,
            headers=self.headers,
        )

    def schedule(self, expense: dict) -> dict:
        return self.client.get(
            f"{self.base}/expenses/{expense['id']}/installments", headers=self.headers
        ).json()


@pytest.fixture
def payoff(client: TestClient, login: Login, monkeypatch: pytest.MonkeyPatch) -> Payoff:
    monkeypatch.setattr(dates, "now", lambda: DECEMBER_1)
    return Payoff(client, login("ana@example.com"))


def test_paying_off_settles_the_purchases_in_the_statement(payoff: Payoff) -> None:
    # Criterio 13, parte de abonos (decisión 28).
    response = payoff.pay_off(period="2026-12")

    assert response.status_code == 201
    body = response.json()
    assert body["period"] == "2026-12"
    [prepayment] = body["prepayments"]
    assert prepayment == {
        "id": prepayment["id"],
        "expense_id": payoff.tv["id"],
        "period": "2026-12",
        "amount": 1000000,
        "reduces": "term",
    }
    # Cuotas de diciembre (422.800) más el saldo de la TV.
    assert body["debt"] == 1422800
    assert [row["period"] for row in payoff.schedule(payoff.tv)["installments"]] == [
        "2026-12"
    ]
    assert payoff.schedule(payoff.mercado)["prepayments"] == []
    # Los zapatos son de después del corte: llegan en enero, sin abono.
    zapatos = payoff.schedule(payoff.zapatos)
    assert zapatos["prepayments"] == []
    assert zapatos["installments"][0]["period"] == "2027-01"


def test_paying_off_twice_has_nothing_to_settle(payoff: Payoff) -> None:
    payoff.pay_off(period="2026-12")

    response = payoff.pay_off(period="2026-12")

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "La tarjeta «Visa» no tiene compras con saldo después de la cuota de "
        "2026-12; no se creó ningún abono."
    )


def test_paying_off_with_a_later_prepayment_creates_nothing(payoff: Payoff) -> None:
    celular = payoff.purchase("Celular", 600000, "2026-11-20", 3)
    payoff.client.post(
        f"{payoff.base}/expenses/{payoff.tv['id']}/prepayments",
        json={"amount": 100000, "period": "2027-02", "reduces": "term"},
        headers=payoff.headers,
    )

    response = payoff.pay_off(period="2027-01")

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "«Compra TV» ya tiene un abono en 2027-02. Bórralo para pagar todo en "
        "2027-01; no se creó ningún abono."
    )
    # Todo o nada: el celular, que sí se podía saldar, queda sin abono.
    assert payoff.schedule(celular)["prepayments"] == []


def test_paying_off_without_period_uses_the_current_month(payoff: Payoff) -> None:
    response = payoff.pay_off()

    assert response.json()["period"] == "2026-12"


def test_an_archived_card_can_be_paid_off(payoff: Payoff) -> None:
    payoff.client.delete(
        f"{payoff.base}/cards/{payoff.card['id']}", headers=payoff.headers
    )

    assert payoff.pay_off(period="2026-12").status_code == 201


def test_paying_off_a_missing_card_is_not_found(payoff: Payoff) -> None:
    assert payoff.pay_off(999, period="2026-12").status_code == 404


def test_paying_off_an_invalid_period_is_rejected(payoff: Payoff) -> None:
    assert payoff.pay_off(period="2026-13").status_code == 422


def test_the_payoff_prepayments_are_deleted_one_by_one(payoff: Payoff) -> None:
    [prepayment] = payoff.pay_off(period="2026-12").json()["prepayments"]

    response = payoff.client.delete(
        f"{payoff.base}/expenses/{payoff.tv['id']}/prepayments/{prepayment['id']}",
        params={"confirm": "true"},
        headers=payoff.headers,
    )

    assert response.status_code == 204
    assert len(payoff.schedule(payoff.tv)["installments"]) == 6


# --- Estado de la tarjeta y simulación (RF-40, RF-41) ---

# 15 de enero de 2027 a mediodía en Bogotá.
JANUARY_15 = datetime(2027, 1, 15, 17, 0, tzinfo=UTC)


@pytest.fixture
def january(
    client: TestClient, login: Login, monkeypatch: pytest.MonkeyPatch
) -> Payoff:
    """La Visa con la "Compra TV", el "Mercado" y los "Zapatos", vista el 15
    de enero de 2027."""
    monkeypatch.setattr(dates, "now", lambda: JANUARY_15)
    return Payoff(client, login("ana@example.com"))


def status_of(space: Payoff, card_id: int | None = None) -> Response:
    return space.client.get(
        f"{space.base}/cards/{card_id or space.card['id']}/status",
        headers=space.headers,
    )


def test_the_status_of_the_card(january: Payoff) -> None:
    # Criterio 10 (RF-40). Los zapatos (1 cuota, 2027-01) también están
    # pendientes en enero.
    response = status_of(january)

    assert response.status_code == 200
    body = response.json()
    assert body["card"] == january.card
    assert body["balance"] == 1150000
    assert body["purchases"] == [
        {
            "expense_id": january.tv["id"],
            "name": "Compra TV",
            "amount": 1200000,
            "spent_on": "2026-11-12",
            "count": 6,
            "next_number": 2,
            "balance": 1000000,
        },
        {
            "expense_id": january.zapatos["id"],
            "name": "Zapatos",
            "amount": 150000,
            "spent_on": "2026-11-30",
            "count": 1,
            "next_number": 1,
            "balance": 150000,
        },
    ]
    assert [(row["period"], row["amount"]) for row in body["months"]] == [
        ("2027-01", 219000 + 150000),
        ("2027-02", 215200),
        ("2027-03", 211400),
        ("2027-04", 207600),
        ("2027-05", 203800),
    ]
    assert body["months"][0] == {
        "period": "2027-01",
        "estimated": 369000,
        "statement": None,
        "prepayments": 0,
        "amount": 369000,
    }


def test_future_statements_and_prepayments_show_up(january: Payoff) -> None:
    january.client.put(
        f"{january.base}/cards/{january.card['id']}/statements/2027-07",
        json={"amount": 15000},
        headers=january.headers,
    )
    january.client.post(
        f"{january.base}/expenses/{january.tv['id']}/prepayments",
        json={"amount": 100000, "period": "2027-03", "reduces": "installment"},
        headers=january.headers,
    )

    months = {row["period"]: row for row in status_of(january).json()["months"]}

    assert months["2027-03"]["prepayments"] == 100000
    assert months["2027-06"]["amount"] == 0
    assert months["2027-07"] == {
        "period": "2027-07",
        "estimated": 0,
        "statement": 15000,
        "prepayments": 0,
        "amount": 15000,
    }


def test_the_status_of_an_archived_card(january: Payoff) -> None:
    january.client.delete(
        f"{january.base}/cards/{january.card['id']}", headers=january.headers
    )

    response = status_of(january)

    assert response.status_code == 200
    assert response.json()["card"]["deleted"] is True


def test_a_card_without_purchases_has_an_empty_status(client: TestClient, ana) -> None:
    headers, space_id = ana
    card = create_card(client, headers, space_id).json()

    body = client.get(
        f"/spaces/{space_id}/cards/{card['id']}/status", headers=headers
    ).json()

    assert (body["balance"], body["purchases"], body["months"]) == (0, [], [])


def simulate(space: Payoff, card_id: int | None = None, **body: object) -> Response:
    return space.client.post(
        f"{space.base}/cards/{card_id or space.card['id']}/simulate",
        json={"amount": 1200000, "installments": 6, **body},
        headers=space.headers,
    )


def test_simulating_a_purchase_saves_nothing(january: Payoff, engine: Engine) -> None:
    # Criterio 10 (RF-41).
    with Session(engine) as db:
        before = db.scalar(select(func.count()).select_from(Expense))

    response = simulate(january, spent_on="2026-11-12")

    assert response.status_code == 200
    body = response.json()
    assert body["first_due_period"] == "2026-12"
    assert [
        (row["number"], row["period"], row["capital"], row["interest"])
        for row in body["installments"]
    ] == [
        (1, "2026-12", 200000, 22800),
        (2, "2027-01", 200000, 19000),
        (3, "2027-02", 200000, 15200),
        (4, "2027-03", 200000, 11400),
        (5, "2027-04", 200000, 7600),
        (6, "2027-05", 200000, 3800),
    ]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Expense)) == before


def test_simulating_without_date_uses_today(january: Payoff) -> None:
    # 15 de enero, corte 25: entra al corte de enero y se paga en febrero.
    body = simulate(january, installments=1).json()

    assert body["first_due_period"] == "2027-02"
    assert body["installments"][0]["interest"] == 0


@pytest.mark.parametrize(
    "body",
    [
        {"installments": 49},
        {"installments": 0},
        {"amount": 0},
        {"amount": 1.5},
        {"spent_on": "2027-01-16"},
    ],
)
def test_an_invalid_simulation_is_rejected(january: Payoff, body: dict) -> None:
    assert simulate(january, **body).status_code == 422


def test_an_archived_card_cannot_be_simulated(january: Payoff) -> None:
    january.client.delete(
        f"{january.base}/cards/{january.card['id']}", headers=january.headers
    )

    response = simulate(january)

    assert response.status_code == 422
    assert "fue eliminada" in response.json()["detail"]


def test_status_and_simulation_of_a_missing_card_are_not_found(
    january: Payoff,
) -> None:
    assert status_of(january, 999).status_code == 404
    assert simulate(january, 999).status_code == 404
