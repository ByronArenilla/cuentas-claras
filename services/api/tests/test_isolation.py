"""Tests que cuidan el principio 5: dos espacios nunca ven los datos del otro.

Los datos observables son los propios espacios, sus membresías (plan 001),
sus categorías (spec 002), sus gastos (spec 003), y sus presupuestos y
resúmenes (spec 004).
"""

import importlib
import pkgutil
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app import dates, routers
from app.deps import member_space
from app.models import Budget, Category, Expense, User
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


def first_category_id(
    client: TestClient, headers: dict[str, str], space_id: int
) -> int:
    response = client.get(f"/spaces/{space_id}/categories", headers=headers)
    return response.json()[0]["id"]


def put_budget(
    client: TestClient,
    headers: dict[str, str],
    space_id: int,
    category_id: int,
    amount: int = 400_000,
) -> Response:
    return client.put(
        f"/spaces/{space_id}/budgets/{category_id}",
        json={"period": "2026-10", "amount": amount},
        headers=headers,
    )


def summary_total(client: TestClient, headers: dict[str, str], space_id: int) -> dict:
    response = client.get(
        f"/spaces/{space_id}/summary", params={"period": "2026-10"}, headers=headers
    )
    assert response.status_code == 200
    return response.json()["total"]


def count_budgets(engine: Engine, space_id: int) -> int:
    query = select(func.count()).where(Budget.space_id == space_id)
    with Session(engine) as db:
        return db.scalar(query)


@pytest.mark.usefixtures("october")
def test_users_in_different_spaces_cannot_touch_each_others_budgets(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # Criterio 6 (RF-17, RF-18): ni fijar presupuestos ni ver el resumen del
    # espacio ajeno, y los datos de una no aparecen en el resumen de la otra.
    ana, bea = login("ana@example.com"), login("bea@example.com")
    ana_space, bea_space = personal(client, ana), personal(client, bea)
    ana_category = first_category_id(client, ana, ana_space)
    bea_category = first_category_id(client, bea, bea_space)
    put_budget(client, ana, ana_space, ana_category, 400_000).raise_for_status()
    put_budget(client, bea, bea_space, bea_category, 900_000).raise_for_status()
    add_expense(client, ana, ana_space, 20_000)
    add_expense(client, bea, bea_space, 70_000)

    for headers, foreign_space, own_space, foreign_category in (
        (ana, bea_space, ana_space, bea_category),
        (bea, ana_space, bea_space, ana_category),
    ):
        by_foreign_route = {
            "fijar": put_budget(client, headers, foreign_space, foreign_category, 1),
            "resumen": client.get(f"/spaces/{foreign_space}/summary", headers=headers),
        }
        for operation, response in by_foreign_route.items():
            assert response.status_code == 404, operation
            assert response.json()["detail"] == "Espacio no encontrado.", operation

        # La categoría ajena tampoco se alcanza desde la ruta del espacio propio.
        response = put_budget(client, headers, own_space, foreign_category, 1)
        assert response.status_code == 404
        assert response.json()["detail"] == "Categoría no encontrada."

    # Nada cambió y cada resumen solo cuenta lo suyo.
    assert count_budgets(engine, ana_space) == count_budgets(engine, bea_space) == 1
    assert summary_total(client, ana, ana_space) == {
        "budget": 400_000,
        "spent": 20_000,
        "remaining": 380_000,
    }
    assert summary_total(client, bea, bea_space) == {
        "budget": 900_000,
        "spent": 70_000,
        "remaining": 830_000,
    }


def test_category_of_space_b_by_route_of_space_a_is_not_found(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # Criterio 7 (RF-9): Ana es miembro de los dos espacios, pero la categoría
    # solo existe en la ruta de su espacio.
    ana = login("ana@example.com")
    space_a = create_space(client, ana, "Casa")
    space_b = create_space(client, ana, "Viajes")
    category_b = first_category_id(client, ana, space_b)

    response = put_budget(client, ana, space_a, category_b)

    assert response.status_code == 404
    assert response.json()["detail"] == "Categoría no encontrada."
    assert count_budgets(engine, space_a) == count_budgets(engine, space_b) == 0


@pytest.mark.usefixtures("october")
def test_deleting_a_space_deletes_only_its_budgets(
    client: TestClient, engine: Engine, login: Login
) -> None:
    # Criterio 9, primera parte (RF-20): mismo usuario, dos espacios.
    ana = login("ana@example.com")
    casa = create_space(client, ana, "Casa")
    viajes = create_space(client, ana, "Viajes")
    put_budget(client, ana, casa, first_category_id(client, ana, casa))
    put_budget(client, ana, viajes, first_category_id(client, ana, viajes))
    add_expense(client, ana, viajes)

    response = client.delete(
        f"/spaces/{viajes}", params={"confirm": "Viajes"}, headers=ana
    )

    assert response.status_code == 204
    assert count_budgets(engine, viajes) == 0
    assert count_budgets(engine, casa) == 1
    assert summary_total(client, ana, casa)["budget"] == 400_000


@pytest.mark.usefixtures("october")
def test_budgets_stay_when_a_member_leaves(
    client: TestClient, shared_space: SharedSpace
) -> None:
    # Criterio 9, segunda parte (RF-19): salir solo borra la membresía.
    space_id, ana, bea = shared_space
    put_budget(client, bea, space_id, first_category_id(client, bea, space_id))

    response = client.delete(f"/spaces/{space_id}/members/me", headers=bea)

    assert response.status_code == 204
    assert summary_total(client, ana, space_id)["budget"] == 400_000
