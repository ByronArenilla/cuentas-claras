"""Tests que cuidan el principio 5: dos espacios nunca ven los datos del otro.

Los datos observables son los propios espacios, sus membresías (plan 001),
sus categorías (spec 002), sus gastos (spec 003), su plan del mes y su
resumen (spec 008: rubros, ingresos, copia y categorías eliminadas), y sus
tarjetas con sus compras, abonos y extractos (spec 009).
"""

import importlib
import pkgutil
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app import dates, routers
from app.deps import member_space
from app.models import (
    BudgetItem,
    Card,
    CardStatement,
    Category,
    Expense,
    Income,
    Prepayment,
    User,
)
from app.models import Session as SessionRow

Login = Callable[..., dict[str, str]]
SharedSpace = tuple[int, dict[str, str], dict[str, str]]


def spaces(client: TestClient, headers: dict[str, str]) -> list[dict]:
    return client.get("/spaces", headers=headers).json()


def create_space(client: TestClient, headers: dict[str, str], name: str) -> int:
    return client.post("/spaces", json={"name": name}, headers=headers).json()["id"]


def category_names(
    client: TestClient, headers: dict[str, str], space_id: int
) -> list[str]:
    response = client.get(f"/spaces/{space_id}/categories", headers=headers)
    return [category["name"] for category in response.json()]


def count_categories(engine: Engine, space_id: int | None = None) -> int:
    """Categorías en la base de datos: las de un espacio o, sin él, todas."""
    query = select(func.count()).select_from(Category)
    if space_id is not None:
        query = query.where(Category.space_id == space_id)
    with Session(engine) as db:
        return db.scalar(query)


def test_users_in_different_spaces_see_nothing_of_each_other(
    client: TestClient, login: Login
) -> None:
    # Criterio de validación 1 (RF-29, RF-30, RF-32).
    ana, bea = login("ana@example.com"), login("bea@example.com")
    casa = create_space(client, ana, "Casa de Ana")
    viajes = create_space(client, bea, "Viajes de Bea")

    ana_view = client.get("/spaces", headers=ana)
    bea_view = client.get("/spaces", headers=bea)

    assert "Viajes de Bea" not in ana_view.text
    assert viajes not in [space["id"] for space in ana_view.json()]
    assert "Casa de Ana" not in bea_view.text
    assert casa not in [space["id"] for space in bea_view.json()]
    assert "bea@example.com" not in client.get("/me", headers=ana).text


def test_foreign_space_answers_like_a_missing_one_on_every_route(
    client: TestClient, login: Login
) -> None:
    # RF-30: ninguna ruta distingue "no existe" de "existe pero no es tuyo".
    ana, bea = login("ana@example.com"), login("bea@example.com")
    foreign = create_space(client, ana, "Casa de Ana")
    missing = foreign + 1000

    for space_id in (foreign, missing):
        requests = [
            client.post(f"/spaces/{space_id}/invitations", headers=bea),
            client.delete(f"/spaces/{space_id}/members/me", headers=bea),
            client.delete(
                f"/spaces/{space_id}",
                params={"confirm": "Casa de Ana"},
                headers=bea,
            ),
            client.get(f"/spaces/{space_id}/categories", headers=bea),
            client.post(
                f"/spaces/{space_id}/categories",
                json={"name": "Mascotas"},
                headers=bea,
            ),
        ]
        for response in requests:
            assert response.status_code == 404
            assert response.json() == {"detail": "Espacio no encontrado."}

    assert [space["name"] for space in spaces(client, ana)] == [
        "Personal",
        "Casa de Ana",
    ]


def test_members_of_the_same_space_see_exactly_the_same(
    client: TestClient, shared_space: SharedSpace
) -> None:
    # Criterio de validación 2 (RF-17, RF-29).
    space_id, ana, bea = shared_space

    [ana_casa] = [space for space in spaces(client, ana) if space["id"] == space_id]
    [bea_casa] = [space for space in spaces(client, bea) if space["id"] == space_id]

    assert ana_casa == bea_casa == {"id": space_id, "name": "Casa"}


def test_members_of_the_same_space_can_both_act_on_it(
    client: TestClient, shared_space: SharedSpace
) -> None:
    # Hoy todos los miembros tienen los mismos permisos (ADR 0001).
    space_id, ana, bea = shared_space

    for headers in (ana, bea):
        response = client.post(f"/spaces/{space_id}/invitations", headers=headers)
        assert response.status_code == 201


def test_deleting_a_space_does_not_touch_another_users_space(
    client: TestClient, login: Login
) -> None:
    # Criterio de validación 6, entre usuarios distintos (RF-27).
    ana, bea = login("ana@example.com"), login("bea@example.com")
    create_space(client, ana, "Casa")
    viajes = create_space(client, bea, "Casa")

    client.delete(f"/spaces/{viajes}", params={"confirm": "Casa"}, headers=bea)

    assert [space["name"] for space in spaces(client, ana)] == ["Personal", "Casa"]
    assert [space["name"] for space in spaces(client, bea)] == ["Personal"]


def test_non_member_cannot_list_or_create_categories(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # Spec 002, criterio de validación 6 (RF-10): amplía el criterio 1 de la
    # 001. El 404 no distingue un espacio ajeno de uno inexistente.
    ana, bea = login("ana@example.com"), login("bea@example.com")
    casa = create_space(client, ana, "Casa de Ana")
    client.post(f"/spaces/{casa}/categories", json={"name": "Mascotas"}, headers=ana)
    before = count_categories(engine)

    for space_id in (casa, casa + 1000):
        listed = client.get(f"/spaces/{space_id}/categories", headers=bea)
        created = client.post(
            f"/spaces/{space_id}/categories", json={"name": "Intrusa"}, headers=bea
        )
        for response in (listed, created):
            assert response.status_code == 404
            assert response.json() == {"detail": "Espacio no encontrado."}
        assert "Mascotas" not in listed.text

    assert count_categories(engine) == before
    assert "Intrusa" not in category_names(client, ana, casa)


def test_deleting_a_space_deletes_only_its_categories(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # Spec 002, criterio de validación 7 (RF-11): amplía el criterio 6 de la
    # 001 con dos espacios del mismo usuario.
    ana = login("ana@example.com")
    casa = create_space(client, ana, "Casa")
    viajes = create_space(client, ana, "Viajes")
    for space_id, name in ((casa, "Mascotas"), (viajes, "Hoteles")):
        client.post(f"/spaces/{space_id}/categories", json={"name": name}, headers=ana)
    casa_before = category_names(client, ana, casa)

    client.delete(f"/spaces/{viajes}", params={"confirm": "Viajes"}, headers=ana)

    assert count_categories(engine, viajes) == 0
    assert category_names(client, ana, casa) == casa_before
    assert casa_before[-1] == "Mascotas"


def depends_on(dependant: Dependant, target: Callable[..., object]) -> bool:
    return any(
        sub.call is target or depends_on(sub, target) for sub in dependant.dependencies
    )


def api_routes() -> list[APIRoute]:
    """Rutas de todos los routers de `app.routers`, incluidos los que añadan
    las specs futuras: se descubren recorriendo el paquete, sin lista fija."""
    routes = []
    for module_info in pkgutil.iter_modules(routers.__path__):
        module = importlib.import_module(f"app.routers.{module_info.name}")
        routes += [r for r in module.router.routes if isinstance(r, APIRoute)]
    return routes


def test_every_route_with_space_id_goes_through_member_space() -> None:
    # RF-29 y RF-32: la única puerta a un espacio es `member_space`. Este test
    # vigila también las rutas que añadan las specs 002 a 004.
    routes = [route for route in api_routes() if "{space_id}" in route.path]

    assert routes, "no hay rutas con {space_id}: el test no vigila nada"
    for route in routes:
        assert depends_on(route.dependant, member_space), route.path


def test_the_api_keeps_no_active_space() -> None:
    # RF-28: el espacio llega en cada petición; ni el usuario ni la sesión
    # guardan un "espacio activo" que pueda desviar un dato a otro espacio.
    for model in (User, SessionRow):
        columns = model.__table__.columns.keys()
        assert not [name for name in columns if "space" in name], model.__name__


# --- Gastos (spec 003) ---

# 15 de octubre de 2026 a mediodía en Bogotá: los gastos sin fecha caen en
# octubre y el listado sin periodo también es octubre.
OCTOBER_15 = datetime(2026, 10, 15, 17, 0, tzinfo=UTC)


@pytest.fixture
def october(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dates, "now", lambda: OCTOBER_15)


def add_expense(
    client: TestClient, headers: dict[str, str], space_id: int, amount: int = 20000
) -> dict:
    """Registra un gasto de hoy en la primera categoría del espacio."""
    categories = client.get(f"/spaces/{space_id}/categories", headers=headers).json()
    body = {
        "amount": amount,
        "payment_type": "debit",
        "category_id": categories[0]["id"],
    }
    response = client.post(f"/spaces/{space_id}/expenses", json=body, headers=headers)
    response.raise_for_status()
    return response.json()


def expense_operations(
    client: TestClient, headers: dict[str, str], space_id: int, expense_id: int
) -> dict[str, object]:
    """Consultar, listar, editar y borrar un gasto por la ruta de `space_id`."""
    url = f"/spaces/{space_id}/expenses"
    return {
        "consultar": client.get(f"{url}/{expense_id}", headers=headers),
        "listar": client.get(url, headers=headers),
        "editar": client.patch(
            f"{url}/{expense_id}", json={"amount": 1}, headers=headers
        ),
        "borrar": client.delete(
            f"{url}/{expense_id}", params={"confirm": "true"}, headers=headers
        ),
    }


def listed_expenses(
    client: TestClient, headers: dict[str, str], space_id: int
) -> list[dict]:
    response = client.get(f"/spaces/{space_id}/expenses", headers=headers)
    assert response.status_code == 200
    return response.json()


def count_expenses(engine: Engine, space_id: int) -> int:
    query = select(func.count()).where(Expense.space_id == space_id)
    with Session(engine) as db:
        return db.scalar(query)


def personal(client: TestClient, headers: dict[str, str]) -> int:
    [space] = spaces(client, headers)
    return space["id"]


@pytest.mark.usefixtures("october")
def test_users_in_different_spaces_cannot_touch_each_others_expenses(
    client: TestClient, login: Login
) -> None:
    # Criterio 1 (RF-12, RF-19): ni por la ruta del espacio ajeno ni pidiendo
    # el gasto ajeno desde el espacio propio.
    ana, bea = login("ana@example.com"), login("bea@example.com")
    ana_space, bea_space = personal(client, ana), personal(client, bea)
    ana_expense = add_expense(client, ana, ana_space)
    bea_expense = add_expense(client, bea, bea_space)

    for headers, foreign_space, own_space, foreign_expense in (
        (ana, bea_space, ana_space, bea_expense),
        (bea, ana_space, bea_space, ana_expense),
    ):
        by_foreign_route = expense_operations(
            client, headers, foreign_space, foreign_expense["id"]
        )
        for operation, response in by_foreign_route.items():
            assert response.status_code == 404, operation
            assert response.json()["detail"] == "Espacio no encontrado.", operation

        by_own_route = expense_operations(
            client, headers, own_space, foreign_expense["id"]
        )
        del by_own_route["listar"]  # El listado del espacio propio es legítimo.
        for operation, response in by_own_route.items():
            assert response.status_code == 404, operation
            assert response.json()["detail"] == "Gasto no encontrado.", operation

    # Nada cambió: cada una sigue viendo solo su gasto, intacto.
    assert listed_expenses(client, ana, ana_space) == [ana_expense]
    assert listed_expenses(client, bea, bea_space) == [bea_expense]


@pytest.mark.usefixtures("october")
def test_expense_of_space_a_by_route_of_space_b_is_not_found(
    client: TestClient, login: Login
) -> None:
    # Criterio 2 (RF-12): Ana es miembro de los dos espacios, pero el gasto
    # solo existe en la ruta de su espacio.
    ana = login("ana@example.com")
    space_a = create_space(client, ana, "Casa")
    space_b = create_space(client, ana, "Viajes")
    expense = add_expense(client, ana, space_a)

    by_route_b = expense_operations(client, ana, space_b, expense["id"])
    del by_route_b["listar"]
    for operation, response in by_route_b.items():
        assert response.status_code == 404, operation
        assert response.json()["detail"] == "Gasto no encontrado.", operation

    assert listed_expenses(client, ana, space_b) == []
    assert listed_expenses(client, ana, space_a) == [expense]


@pytest.mark.usefixtures("october")
def test_deleting_a_space_deletes_only_its_expenses(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # Criterio 6 (RF-21): mismo usuario, dos espacios.
    ana = login("ana@example.com")
    casa = create_space(client, ana, "Casa")
    viajes = create_space(client, ana, "Viajes")
    kept = add_expense(client, ana, casa)
    add_expense(client, ana, viajes)
    add_expense(client, ana, viajes)

    response = client.delete(
        f"/spaces/{viajes}", params={"confirm": "Viajes"}, headers=ana
    )

    assert response.status_code == 204
    assert count_expenses(engine, viajes) == 0
    assert listed_expenses(client, ana, casa) == [kept]


@pytest.mark.usefixtures("october")
def test_expenses_of_a_member_who_leaves_stay_with_their_author(
    client: TestClient, shared_space: SharedSpace
) -> None:
    # Criterio 7 (RF-20): salir solo borra la membresía.
    space_id, ana, bea = shared_space
    bea_id = client.get("/me", headers=bea).json()["id"]
    expense = add_expense(client, bea, space_id)

    response = client.delete(f"/spaces/{space_id}/members/me", headers=bea)

    assert response.status_code == 204
    assert listed_expenses(client, ana, space_id) == [expense]
    assert expense["created_by"] == bea_id


# --- Presupuestos y resumen (spec 004) ---
# Salieron con la ruta de presupuestos de la 004 (spec 008, RF-27). Los
# reemplazan los tests del plan del mes del final de este archivo.


@pytest.mark.usefixtures("october")
def test_recent_expenses_never_cross_spaces(client: TestClient, login: Login) -> None:
    # RF-4 de la 006: ni por la ruta ajena, ni mezclando espacios propios.
    ana, bea = login("ana@example.com"), login("bea@example.com")
    ana_space, bea_space = personal(client, ana), personal(client, bea)
    casa = create_space(client, ana, "Casa")
    ana_expense = add_expense(client, ana, ana_space)
    add_expense(client, ana, casa)
    add_expense(client, bea, bea_space)

    foreign = client.get(f"/spaces/{bea_space}/expenses/recent", headers=ana)
    own = client.get(f"/spaces/{ana_space}/expenses/recent", headers=ana)

    assert foreign.status_code == 404
    assert foreign.json()["detail"] == "Espacio no encontrado."
    assert own.json() == [ana_expense]


# --- Plan del mes: rubros, ingresos, copia y resumen (spec 008) ---


class Plan:
    """Rubro, ingreso y gasto planeado de octubre en un espacio."""

    def __init__(self, client: TestClient, headers: dict[str, str], space_id: int):
        self.space_id = space_id
        listed = client.get(f"/spaces/{space_id}/categories", headers=headers)
        self.category = listed.json()[0]["id"]
        self.item = client.post(
            f"/spaces/{space_id}/budget-items",
            json={
                "period": "2026-10",
                "name": "Mercado",
                "category_id": self.category,
                "amount": 800_000,
            },
            headers=headers,
        ).json()
        self.income = client.post(
            f"/spaces/{space_id}/incomes",
            json={"period": "2026-10", "name": "Salario", "amount": 5_000_000},
            headers=headers,
        ).json()
        client.post(
            f"/spaces/{space_id}/expenses",
            json={
                "amount": 30_000,
                "payment_type": "debit",
                "budget_item_id": self.item["id"],
            },
            headers=headers,
        ).raise_for_status()


def plan_total(client: TestClient, headers: dict[str, str], space_id: int) -> dict:
    response = client.get(
        f"/spaces/{space_id}/summary", params={"period": "2026-10"}, headers=headers
    )
    assert response.status_code == 200
    return response.json()["total"]


def count_plan(engine: Engine, space_id: int) -> tuple[int, int]:
    with Session(engine) as db:
        return tuple(
            db.scalar(select(func.count()).where(model.space_id == space_id))
            for model in (BudgetItem, Income)
        )


@pytest.mark.usefixtures("october")
def test_users_in_different_spaces_cannot_touch_each_others_plan(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # Criterio 12 (RF-9, RF-12, RF-28, RF-29): nada por la ruta ajena, nada
    # ajeno por la ruta propia, y cada resumen solo cuenta lo suyo.
    ana, bea = login("ana@example.com"), login("bea@example.com")
    plans = {
        "ana": Plan(client, ana, personal(client, ana)),
        "bea": Plan(client, bea, personal(client, bea)),
    }

    for headers, own, foreign in (
        (ana, plans["ana"], plans["bea"]),
        (bea, plans["bea"], plans["ana"]),
    ):
        base = f"/spaces/{foreign.space_id}"
        item_url = f"{base}/budget-items/{foreign.item['id']}"
        income_url = f"{base}/incomes/{foreign.income['id']}"
        by_foreign_route = {
            "crear rubro": client.post(
                f"{base}/budget-items",
                json={"name": "X", "category_id": foreign.category, "amount": 1},
                headers=headers,
            ),
            "editar rubro": client.patch(item_url, json={"amount": 1}, headers=headers),
            "borrar rubro": client.delete(item_url, headers=headers),
            "crear ingreso": client.post(
                f"{base}/incomes", json={"name": "X", "amount": 1}, headers=headers
            ),
            "editar ingreso": client.patch(
                income_url, json={"amount": 1}, headers=headers
            ),
            "borrar ingreso": client.delete(income_url, headers=headers),
            "copiar": client.post(
                f"{base}/plan/copy", json={"period": "2026-11"}, headers=headers
            ),
            "resumen": client.get(f"{base}/summary", headers=headers),
            "eliminar categoría": client.delete(
                f"{base}/categories/{foreign.category}", headers=headers
            ),
        }
        for operation, response in by_foreign_route.items():
            assert response.status_code == 404, operation
            assert response.json()["detail"] == "Espacio no encontrado.", operation

        # Lo ajeno tampoco se alcanza desde la ruta del espacio propio.
        own_base = f"/spaces/{own.space_id}"
        by_own_route = {
            "Rubro no encontrado.": [
                client.patch(
                    f"{own_base}/budget-items/{foreign.item['id']}",
                    json={"amount": 1},
                    headers=headers,
                ),
                client.delete(
                    f"{own_base}/budget-items/{foreign.item['id']}", headers=headers
                ),
            ],
            "Ingreso no encontrado.": [
                client.patch(
                    f"{own_base}/incomes/{foreign.income['id']}",
                    json={"amount": 1},
                    headers=headers,
                ),
                client.delete(
                    f"{own_base}/incomes/{foreign.income['id']}", headers=headers
                ),
            ],
            "Categoría no encontrada.": [
                client.delete(
                    f"{own_base}/categories/{foreign.category}", headers=headers
                )
            ],
        }
        for detail, responses in by_own_route.items():
            for response in responses:
                assert response.status_code == 404, detail
                assert response.json()["detail"] == detail
        foreign_category = client.post(
            f"{own_base}/budget-items",
            json={"name": "X", "category_id": foreign.category, "amount": 1},
            headers=headers,
        )
        assert foreign_category.status_code == 422

    # Nada cambió y cada resumen solo cuenta lo suyo.
    for name, headers in (("ana", ana), ("bea", bea)):
        space_id = plans[name].space_id
        assert count_plan(engine, space_id) == (1, 1)
        assert plan_total(client, headers, space_id) == {
            "income": 5_000_000,
            "planned": 800_000,
            "debts": 0,
            "spent_planned": 30_000,
            "spent_unplanned": 0,
            "spent": 30_000,
            "unassigned": 4_200_000,
            "balance": 4_970_000,
        }
    with Session(engine) as db:
        assert (
            db.scalar(select(func.count()).where(Category.deleted_at.is_not(None))) == 0
        )


@pytest.mark.usefixtures("october")
def test_an_item_of_space_b_cannot_be_used_in_space_a(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # RF-18: Ana es miembro de los dos espacios, pero el rubro es de Viajes.
    ana = login("ana@example.com")
    casa = create_space(client, ana, "Casa")
    viajes = Plan(client, ana, create_space(client, ana, "Viajes"))
    casa_category = client.get(f"/spaces/{casa}/categories", headers=ana).json()[0]

    response = client.post(
        f"/spaces/{casa}/expenses",
        json={
            "amount": 10_000,
            "payment_type": "debit",
            "budget_item_id": viajes.item["id"],
        },
        headers=ana,
    )
    moved = client.post(
        f"/spaces/{casa}/expenses",
        json={
            "amount": 10_000,
            "payment_type": "debit",
            "category_id": casa_category["id"],
        },
        headers=ana,
    ).json()
    relinked = client.patch(
        f"/spaces/{casa}/expenses/{moved['id']}",
        json={"budget_item_id": viajes.item["id"]},
        headers=ana,
    )

    for rejected in (response, relinked):
        assert rejected.status_code == 422
        assert rejected.json()["detail"] == "El rubro no existe en este espacio."
    assert count_expenses(engine, casa) == 1


@pytest.mark.usefixtures("october")
def test_deleting_a_space_deletes_only_its_plan(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # RF-30: mismo usuario, dos espacios, con gastos ligados a rubros.
    ana = login("ana@example.com")
    casa = Plan(client, ana, create_space(client, ana, "Casa"))
    viajes = Plan(client, ana, create_space(client, ana, "Viajes"))

    response = client.delete(
        f"/spaces/{viajes.space_id}", params={"confirm": "Viajes"}, headers=ana
    )

    assert response.status_code == 204
    assert count_plan(engine, viajes.space_id) == (0, 0)
    assert count_plan(engine, casa.space_id) == (1, 1)
    assert plan_total(client, ana, casa.space_id)["planned"] == 800_000


@pytest.mark.usefixtures("october")
def test_the_plan_stays_when_a_member_leaves(
    client: TestClient, shared_space: SharedSpace
) -> None:
    # RF-30: salir solo borra la membresía.
    space_id, ana, bea = shared_space
    Plan(client, bea, space_id)

    response = client.delete(f"/spaces/{space_id}/members/me", headers=bea)

    assert response.status_code == 204
    total = plan_total(client, ana, space_id)
    assert (total["income"], total["planned"], total["spent"]) == (
        5_000_000,
        800_000,
        30_000,
    )


# --- Tarjetas, abonos y extractos (spec 009) ---

# 1 de diciembre de 2026 a mediodía en Bogotá.
DECEMBER_1 = datetime(2026, 12, 1, 17, 0, tzinfo=UTC)


@pytest.fixture
def december(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dates, "now", lambda: DECEMBER_1)


class CardSpace:
    """La Visa del espacio con la "Compra TV" a 6 cuotas, un valor real del
    extracto en diciembre y un abono en diciembre: deuda de 831.500."""

    def __init__(
        self, client: TestClient, headers: dict[str, str], space_id: int
    ) -> None:
        self.space_id = space_id
        base = f"/spaces/{space_id}"
        category = client.get(f"{base}/categories", headers=headers).json()[0]["id"]
        self.card = client.post(
            f"{base}/cards",
            json={"name": "Visa", "cutoff_day": 25, "due_day": 10, "monthly_rate": 1.9},
            headers=headers,
        ).json()
        self.purchase = client.post(
            f"{base}/expenses",
            json={
                "payment_type": "credit",
                "card_id": self.card["id"],
                "category_id": category,
                "description": "Compra TV",
                "amount": 1_200_000,
                "installments": 6,
                "spent_on": "2026-11-12",
            },
            headers=headers,
        ).json()
        client.put(
            f"{base}/cards/{self.card['id']}/statements/2026-12",
            json={"amount": 431_500},
            headers=headers,
        ).raise_for_status()
        self.prepayment = client.post(
            f"{base}/expenses/{self.purchase['id']}/prepayments",
            json={"amount": 400_000, "period": "2026-12", "reduces": "term"},
            headers=headers,
        ).json()["prepayment"]


def december_debts(
    client: TestClient, headers: dict[str, str], space_id: int
) -> list[tuple[int, int]]:
    response = client.get(
        f"/spaces/{space_id}/summary", params={"period": "2026-12"}, headers=headers
    )
    assert response.status_code == 200
    return [(debt["card_id"], debt["amount"]) for debt in response.json()["debts"]]


def count_card_data(engine: Engine, space_id: int) -> tuple[int, int, int]:
    with Session(engine) as db:
        return tuple(
            db.scalar(select(func.count()).where(model.space_id == space_id))
            for model in (Card, Prepayment, CardStatement)
        )


def card_operations(
    client: TestClient, headers: dict[str, str], base: str, foreign: "CardSpace"
) -> dict[str, object]:
    """Cada operación sobre la tarjeta, la compra y el abono de `foreign`,
    por la ruta de `base`."""
    card = f"{base}/cards/{foreign.card['id']}"
    expense = f"{base}/expenses/{foreign.purchase['id']}"
    return {
        "editar tarjeta": client.patch(card, json={"cutoff_day": 1}, headers=headers),
        "eliminar tarjeta": client.delete(card, headers=headers),
        "estado": client.get(f"{card}/status", headers=headers),
        "simular": client.post(f"{card}/simulate", json={"amount": 1}, headers=headers),
        "escribir extracto": client.put(
            f"{card}/statements/2026-12", json={"amount": 1}, headers=headers
        ),
        "quitar extracto": client.delete(f"{card}/statements/2026-12", headers=headers),
        "pagar todo": client.post(
            f"{card}/payoff", json={"period": "2026-12"}, headers=headers
        ),
        "plan de cuotas": client.get(f"{expense}/installments", headers=headers),
        "abonar": client.post(
            f"{expense}/prepayments",
            json={"amount": 1, "period": "2027-01", "reduces": "term"},
            headers=headers,
        ),
        "borrar abono": client.delete(
            f"{expense}/prepayments/{foreign.prepayment['id']}",
            params={"confirm": "true"},
            headers=headers,
        ),
    }


@pytest.mark.usefixtures("december")
def test_users_in_different_spaces_cannot_touch_each_others_cards(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # Criterio 12 de la 009 (RF-8, RF-42, RF-43).
    ana, bea = login("ana@example.com"), login("bea@example.com")
    spaces_of = {
        "ana": CardSpace(client, ana, personal(client, ana)),
        "bea": CardSpace(client, bea, personal(client, bea)),
    }

    for headers, own, foreign in (
        (ana, spaces_of["ana"], spaces_of["bea"]),
        (bea, spaces_of["bea"], spaces_of["ana"]),
    ):
        foreign_base = f"/spaces/{foreign.space_id}"
        by_foreign_route = {
            **card_operations(client, headers, foreign_base, foreign),
            "crear tarjeta": client.post(
                f"{foreign_base}/cards",
                json={"name": "X", "cutoff_day": 1, "due_day": 2},
                headers=headers,
            ),
            "listar tarjetas": client.get(f"{foreign_base}/cards", headers=headers),
        }
        for operation, response in by_foreign_route.items():
            assert response.status_code == 404, operation
            assert response.json()["detail"] == "Espacio no encontrado.", operation

        # Lo ajeno tampoco se alcanza desde la ruta del espacio propio.
        own_route = card_operations(client, headers, f"/spaces/{own.space_id}", foreign)
        for operation, response in own_route.items():
            assert response.status_code == 404, operation
            assert response.json()["detail"] in (
                "Tarjeta no encontrada.",
                "Gasto no encontrado.",
            ), operation
        own_prepayment = client.delete(
            f"/spaces/{own.space_id}/expenses/{own.purchase['id']}"
            f"/prepayments/{foreign.prepayment['id']}",
            params={"confirm": "true"},
            headers=headers,
        )
        assert own_prepayment.json()["detail"] == "Abono no encontrado."

    # Nada cambió y cada resumen solo trae sus propias deudas.
    for name, headers in (("ana", ana), ("bea", bea)):
        own = spaces_of[name]
        assert count_card_data(engine, own.space_id) == (1, 1, 1)
        assert december_debts(client, headers, own.space_id) == [
            (own.card["id"], 831_500)
        ]
        cards = client.get(f"/spaces/{own.space_id}/cards", headers=headers).json()
        assert [card["id"] for card in cards] == [own.card["id"]]


@pytest.mark.usefixtures("december")
def test_a_card_of_space_b_cannot_be_used_in_space_a(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # RF-12, RF-43: Ana es miembro de los dos espacios, pero la tarjeta es de
    # Viajes.
    ana = login("ana@example.com")
    casa = create_space(client, ana, "Casa")
    viajes = CardSpace(client, ana, create_space(client, ana, "Viajes"))
    category = client.get(f"/spaces/{casa}/categories", headers=ana).json()[0]["id"]
    body = {
        "payment_type": "credit",
        "card_id": viajes.card["id"],
        "category_id": category,
        "description": "Hotel",
        "amount": 10_000,
    }

    created = client.post(f"/spaces/{casa}/expenses", json=body, headers=ana)
    debit = client.post(
        f"/spaces/{casa}/expenses",
        json={"amount": 10_000, "payment_type": "debit", "category_id": category},
        headers=ana,
    ).json()
    moved = client.patch(
        f"/spaces/{casa}/expenses/{debit['id']}",
        json={
            "payment_type": "credit",
            "card_id": viajes.card["id"],
            "description": "Hotel",
        },
        headers=ana,
    )

    for rejected in (created, moved):
        assert rejected.status_code == 422
        assert rejected.json()["detail"] == "La tarjeta no existe en este espacio."
    assert count_expenses(engine, casa) == 1
    assert december_debts(client, ana, casa) == []


@pytest.mark.usefixtures("december")
def test_deleting_a_space_deletes_only_its_cards(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # RF-44: mismo usuario, dos espacios, con compras, abonos y extractos.
    ana = login("ana@example.com")
    casa = CardSpace(client, ana, create_space(client, ana, "Casa"))
    viajes = CardSpace(client, ana, create_space(client, ana, "Viajes"))

    response = client.delete(
        f"/spaces/{viajes.space_id}", params={"confirm": "Viajes"}, headers=ana
    )

    assert response.status_code == 204
    assert count_card_data(engine, viajes.space_id) == (0, 0, 0)
    assert count_card_data(engine, casa.space_id) == (1, 1, 1)
    assert december_debts(client, ana, casa.space_id) == [(casa.card["id"], 831_500)]


@pytest.mark.usefixtures("december")
def test_cards_stay_when_a_member_leaves(
    client: TestClient, shared_space: SharedSpace
) -> None:
    # RF-44: lo que registró Bea sigue en el resumen de Ana.
    space_id, ana, bea = shared_space
    bea_cards = CardSpace(client, bea, space_id)

    response = client.delete(f"/spaces/{space_id}/members/me", headers=bea)

    assert response.status_code == 204
    assert december_debts(client, ana, space_id) == [(bea_cards.card["id"], 831_500)]
