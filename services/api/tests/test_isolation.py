"""Tests que cuidan el principio 5: dos espacios nunca ven los datos del otro.

Todavía no hay gastos, así que el dato observable son los propios espacios y
sus membresías (plan 001). Las specs 002 a 004 ampliarán estos tests con
gastos, categorías y presupuestos reales.
"""

import importlib
import pkgutil
from collections.abc import Callable

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import routers
from app.deps import member_space
from app.models import Session as SessionRow
from app.models import User

Login = Callable[..., dict[str, str]]
SharedSpace = tuple[int, dict[str, str], dict[str, str]]


def spaces(client: TestClient, headers: dict[str, str]) -> list[dict]:
    return client.get("/spaces", headers=headers).json()


def create_space(client: TestClient, headers: dict[str, str], name: str) -> int:
    return client.post("/spaces", json={"name": name}, headers=headers).json()["id"]


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
