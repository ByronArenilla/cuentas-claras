"""Resumen del plan del mes, sin HTTP (spec 008, RF-23 a RF-25; principio 10)."""

from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BudgetItem, Category, Expense, Income, Space, User, utc_now
from app.summary import build_summary, spent_by_category, spent_by_item

NOVEMBER = (date(2026, 11, 1), date(2026, 12, 1))


@pytest.fixture
def space(session: Session) -> Space:
    space = Space(name="Casa")
    session.add(space)
    session.flush()
    return space


@pytest.fixture
def user(session: Session) -> User:
    user = User(email="ana@example.com", password_hash="hash")
    session.add(user)
    session.flush()
    return user


def add_category(session: Session, space: Space, name: str) -> Category:
    category = Category(space_id=space.id, name=name)
    session.add(category)
    session.flush()
    return category


def add_item(
    session: Session,
    category: Category,
    name: str,
    amount: int,
    month: date = NOVEMBER[0],
) -> BudgetItem:
    item = BudgetItem(
        space_id=category.space_id,
        period_start=month,
        name=name,
        category_id=category.id,
        amount=amount,
    )
    session.add(item)
    session.flush()
    return item


def add_income(
    session: Session, space: Space, name: str, amount: int, month: date = NOVEMBER[0]
) -> Income:
    income = Income(space_id=space.id, period_start=month, name=name, amount=amount)
    session.add(income)
    session.flush()
    return income


def spend(
    session: Session,
    user: User,
    amount: int,
    day: date,
    *,
    item: BudgetItem | None = None,
    category: Category | None = None,
) -> None:
    """Un gasto planeado (con `item`) o no planeado (con `category`)."""
    category_id = item.category_id if item is not None else category.id
    space_id = item.space_id if item is not None else category.space_id
    session.add(
        Expense(
            space_id=space_id,
            category_id=category_id,
            budget_item_id=item.id if item is not None else None,
            created_by=user.id,
            amount=amount,
            payment_type="debit",
            spent_on=day,
        )
    )
    session.flush()


@pytest.fixture
def november(session: Session, space: Space, user: User) -> dict:
    """El mes del criterio 1.

    - Ingresos: Salario 5.000.000.
    - Rubros: Arriendo (Hogar) 1.500.000 y Mercado (Comida) 800.000.
    - Gastos planeados: Arriendo 1.500.000; Mercado 412.000 + 400.000, que lo
      exceden en 12.000.
    - Gastos no planeados: Transporte 38.000 y Comida 10.000.
    """
    hogar = add_category(session, space, "Hogar")
    comida = add_category(session, space, "Comida")
    transporte = add_category(session, space, "Transporte")
    salud = add_category(session, space, "Salud")
    salario = add_income(session, space, "Salario", 5_000_000)
    arriendo = add_item(session, hogar, "Arriendo", 1_500_000)
    mercado = add_item(session, comida, "Mercado", 800_000)
    spend(session, user, 1_500_000, date(2026, 11, 1), item=arriendo)
    spend(session, user, 412_000, date(2026, 11, 3), item=mercado)
    spend(session, user, 400_000, date(2026, 11, 30), item=mercado)
    spend(session, user, 38_000, date(2026, 11, 10), category=transporte)
    spend(session, user, 10_000, date(2026, 11, 11), category=comida)
    # Fuera de noviembre: no cuentan.
    spend(session, user, 99_000, date(2026, 10, 31), category=comida)
    spend(session, user, 99_000, date(2026, 12, 1), category=comida)
    return {
        "hogar": hogar,
        "comida": comida,
        "transporte": transporte,
        "salud": salud,
        "salario": salario,
        "arriendo": arriendo,
        "mercado": mercado,
    }


# --- Gastado ---


def test_spent_by_item_adds_only_planned_expenses_of_the_month(
    session: Session, space: Space, november: dict
) -> None:
    spent = spent_by_item(session, space.id, *NOVEMBER)

    assert spent == {
        november["arriendo"].id: 1_500_000,
        november["mercado"].id: 812_000,
    }
    assert all(type(value) is int for value in spent.values())


def test_spent_by_category_adds_planned_and_unplanned(
    session: Session, space: Space, november: dict
) -> None:
    spent = spent_by_category(session, space.id, *NOVEMBER)

    assert spent == {
        november["hogar"].id: 1_500_000,
        november["comida"].id: 822_000,
        november["transporte"].id: 38_000,
    }


# --- Resumen (criterio 1) ---


def test_the_summary_of_the_month(
    session: Session, space: Space, november: dict
) -> None:
    summary = build_summary(session, space.id, "2026-11").model_dump()

    assert summary["period"] == "2026-11"
    assert summary["incomes"] == [
        {"id": november["salario"].id, "name": "Salario", "amount": 5_000_000}
    ]
    assert summary["budget_items"] == [
        {
            "id": november["arriendo"].id,
            "name": "Arriendo",
            "category_id": november["hogar"].id,
            "planned": 1_500_000,
            "spent": 1_500_000,
            "remaining": 0,
        },
        {
            "id": november["mercado"].id,
            "name": "Mercado",
            "category_id": november["comida"].id,
            "planned": 800_000,
            "spent": 812_000,
            "remaining": -12_000,
        },
    ]
    assert summary["categories"] == [
        {
            "category_id": november["hogar"].id,
            "name": "Hogar",
            "planned": 1_500_000,
            "spent": 1_500_000,
            "deleted": False,
        },
        {
            "category_id": november["comida"].id,
            "name": "Comida",
            "planned": 800_000,
            "spent": 822_000,
            "deleted": False,
        },
        {
            "category_id": november["transporte"].id,
            "name": "Transporte",
            "planned": 0,
            "spent": 38_000,
            "deleted": False,
        },
        {
            "category_id": november["salud"].id,
            "name": "Salud",
            "planned": 0,
            "spent": 0,
            "deleted": False,
        },
    ]
    assert summary["total"] == {
        "income": 5_000_000,
        "planned": 2_300_000,
        "spent_planned": 2_312_000,
        "spent_unplanned": 48_000,
        "spent": 2_360_000,
        "unassigned": 2_700_000,
        "balance": 2_640_000,
    }


def test_unassigned_and_balance_can_be_negative(
    session: Session, space: Space, user: User
) -> None:
    # RF-24: se planeó y se gastó más de lo que entra.
    hogar = add_category(session, space, "Hogar")
    add_income(session, space, "Salario", 1_000_000)
    item = add_item(session, hogar, "Arriendo", 1_500_000)
    spend(session, user, 1_200_000, date(2026, 11, 5), item=item)

    total = build_summary(session, space.id, "2026-11").total

    assert total.unassigned == -500_000
    assert total.balance == -200_000


def test_all_amounts_are_ints(session: Session, space: Space, november: dict) -> None:
    summary = build_summary(session, space.id, "2026-11").model_dump()
    amounts = [
        *[row["amount"] for row in summary["incomes"]],
        *[
            row[key]
            for row in summary["budget_items"]
            for key in ("planned", "spent", "remaining")
        ],
        *[row[key] for row in summary["categories"] for key in ("planned", "spent")],
        *summary["total"].values(),
    ]

    assert all(type(amount) is int for amount in amounts)


# --- Mes sin plan (RF-25, decisión 10) ---


def test_a_month_without_plan_is_empty_and_creates_nothing(
    session: Session, space: Space, november: dict
) -> None:
    summary = build_summary(session, space.id, "2027-01").model_dump()

    assert summary["incomes"] == []
    assert summary["budget_items"] == []
    assert [row["planned"] for row in summary["categories"]] == [0, 0, 0, 0]
    assert summary["total"] == {
        "income": 0,
        "planned": 0,
        "spent_planned": 0,
        "spent_unplanned": 0,
        "spent": 0,
        "unassigned": 0,
        "balance": 0,
    }
    assert session.scalar(select(func.count()).select_from(BudgetItem)) == 2
    assert session.scalar(select(func.count()).select_from(Income)) == 1


def test_a_space_without_categories_has_an_empty_summary(
    session: Session, space: Space
) -> None:
    summary = build_summary(session, space.id, "2026-11")

    assert summary.categories == []
    assert summary.total.spent == 0


# --- Categorías eliminadas (decisión 18, RF-40) ---


def test_a_deleted_category_shows_only_where_it_has_data(
    session: Session, space: Space, user: User
) -> None:
    mascotas = add_category(session, space, "Mascotas")
    viajes = add_category(session, space, "Viajes")
    add_item(session, mascotas, "Comida perro", 120_000)
    spend(session, user, 50_000, date(2026, 10, 2), category=viajes)
    mascotas.deleted_at = viajes.deleted_at = utc_now()
    session.flush()

    def rows(period: str) -> list[tuple[str, bool]]:
        summary = build_summary(session, space.id, period)
        return [(row.name, row.deleted) for row in summary.categories]

    # Mascotas tiene un rubro en noviembre; Viajes, un gasto en octubre.
    assert rows("2026-11") == [("Mascotas", True)]
    assert rows("2026-10") == [("Viajes", True)]
    assert rows("2026-12") == []


def test_a_deleted_category_still_counts_in_the_totals(
    session: Session, space: Space, user: User
) -> None:
    mascotas = add_category(session, space, "Mascotas")
    item = add_item(session, mascotas, "Comida perro", 120_000)
    spend(session, user, 130_000, date(2026, 11, 2), item=item)
    mascotas.deleted_at = utc_now()
    session.flush()

    summary = build_summary(session, space.id, "2026-11")

    assert summary.budget_items[0].remaining == -10_000
    assert summary.total.planned == 120_000
    assert summary.total.spent == 130_000


# --- Aislamiento (RF-29) ---


def test_nothing_from_another_space_is_counted(
    session: Session, space: Space, user: User, november: dict
) -> None:
    other = Space(name="Viajes")
    session.add(other)
    session.flush()
    hoteles = add_category(session, other, "Hoteles")
    add_income(session, other, "Salario", 9_000_000)
    item = add_item(session, hoteles, "Hotel", 700_000)
    spend(session, user, 650_000, date(2026, 11, 20), item=item)

    summary = build_summary(session, space.id, "2026-11")

    assert [row.name for row in summary.categories] == [
        "Hogar",
        "Comida",
        "Transporte",
        "Salud",
    ]
    assert summary.total.income == 5_000_000
    assert summary.total.planned == 2_300_000
    assert summary.total.spent == 2_360_000
