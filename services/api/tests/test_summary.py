"""Presupuesto vigente y resumen, sin HTTP (spec 004, T3; principio 10)."""

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.models import Budget, Category, Expense, Space, User
from app.summary import build_summary, effective_budgets, spent_by_category

OCTOBER = (date(2026, 10, 1), date(2026, 11, 1))


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


def set_budget(
    session: Session, category: Category, period: str, amount: int | None
) -> None:
    year, month = map(int, period.split("-"))
    session.add(
        Budget(
            space_id=category.space_id,
            category_id=category.id,
            starts_on=date(year, month, 1),
            amount=amount,
        )
    )
    session.flush()


def spend(
    session: Session, category: Category, user: User, amount: int, day: date
) -> None:
    session.add(
        Expense(
            space_id=category.space_id,
            category_id=category.id,
            created_by=user.id,
            amount=amount,
            payment_type="debit",
            spent_on=day,
        )
    )
    session.flush()


def budget_in(session: Session, category: Category, period: str) -> int | None:
    year, month = map(int, period.split("-"))
    budgets = effective_budgets(session, category.space_id, date(year, month, 1))
    return budgets.get(category.id)


# --- Presupuesto vigente ---


def test_a_budget_rules_from_its_period_onwards(session: Session, space: Space) -> None:
    # Criterio 1, primera parte (RF-3).
    comida = add_category(session, space, "Comida")
    set_budget(session, comida, "2026-09", 400_000)

    assert budget_in(session, comida, "2026-08") is None
    for period in ("2026-09", "2026-10", "2026-11", "2026-12", "2027-06"):
        assert budget_in(session, comida, period) == 400_000


def test_a_later_change_does_not_touch_earlier_periods(
    session: Session, space: Space
) -> None:
    # Criterio 1, segunda parte (RF-3, RF-4).
    comida = add_category(session, space, "Comida")
    set_budget(session, comida, "2026-09", 400_000)
    set_budget(session, comida, "2026-11", 500_000)

    assert budget_in(session, comida, "2026-09") == 400_000
    assert budget_in(session, comida, "2026-10") == 400_000
    assert budget_in(session, comida, "2026-11") == 500_000
    assert budget_in(session, comida, "2026-12") == 500_000


def test_an_earlier_change_does_not_touch_later_changes(
    session: Session, space: Space
) -> None:
    # RF-4: fijar un mes pasado no pisa los meses desde los que ya hay otro,
    # aunque se guarde después.
    comida = add_category(session, space, "Comida")
    set_budget(session, comida, "2026-11", 500_000)
    set_budget(session, comida, "2026-09", 400_000)

    assert budget_in(session, comida, "2026-10") == 400_000
    assert budget_in(session, comida, "2026-11") == 500_000


def test_removing_a_budget_rules_until_the_next_change(
    session: Session, space: Space
) -> None:
    # Criterio 2 (RF-6): una fila nula quita el presupuesto desde ese mes.
    comida = add_category(session, space, "Comida")
    set_budget(session, comida, "2026-09", 400_000)
    set_budget(session, comida, "2026-11", 500_000)
    set_budget(session, comida, "2026-12", None)

    assert budget_in(session, comida, "2026-11") == 500_000
    assert budget_in(session, comida, "2026-12") is None
    assert budget_in(session, comida, "2027-01") is None

    set_budget(session, comida, "2027-02", 300_000)
    assert budget_in(session, comida, "2027-02") == 300_000


def test_each_category_has_its_own_budget(session: Session, space: Space) -> None:
    comida, ocio = (
        add_category(session, space, "Comida"),
        add_category(session, space, "Ocio"),
    )
    set_budget(session, comida, "2026-09", 400_000)
    set_budget(session, ocio, "2026-10", 100_000)

    assert effective_budgets(session, space.id, date(2026, 9, 1)) == {
        comida.id: 400_000
    }
    assert effective_budgets(session, space.id, date(2026, 10, 1)) == {
        comida.id: 400_000,
        ocio.id: 100_000,
    }


# --- Gastado ---


def test_spent_only_adds_the_expenses_of_the_period(
    session: Session, space: Space, user: User
) -> None:
    # Criterio 3, bordes del mes (RF-12, regla de RF-9 de la 003).
    comida = add_category(session, space, "Comida")
    spend(session, comida, user, 1_000, date(2026, 9, 30))
    spend(session, comida, user, 20_000, date(2026, 10, 1))
    spend(session, comida, user, 30_000, date(2026, 10, 31))
    spend(session, comida, user, 4_000, date(2026, 11, 1))

    assert spent_by_category(session, space.id, *OCTOBER) == {comida.id: 50_000}


def test_spent_is_an_int(session: Session, space: Space, user: User) -> None:
    # RF-16: `SUM` de PostgreSQL devolvería `Decimal` (plan 004).
    comida = add_category(session, space, "Comida")
    spend(session, comida, user, 20_000, date(2026, 10, 1))

    total = spent_by_category(session, space.id, *OCTOBER)[comida.id]
    assert type(total) is int


# --- Resumen ---


def test_summary_lists_every_category_with_budget_spent_and_remaining(
    session: Session, space: Space, user: User
) -> None:
    # Criterio 3 (RF-11 a RF-14).
    comida = add_category(session, space, "Comida")
    transporte = add_category(session, space, "Transporte")
    ocio = add_category(session, space, "Ocio")
    salud = add_category(session, space, "Salud")
    set_budget(session, comida, "2026-09", 400_000)
    set_budget(session, ocio, "2026-10", 100_000)
    spend(session, comida, user, 412_000, date(2026, 10, 15))
    spend(session, transporte, user, 38_000, date(2026, 10, 2))
    spend(session, salud, user, 9_000, date(2026, 11, 1))  # Otro mes.

    summary = build_summary(session, space.id, "2026-10")

    assert summary.period == "2026-10"
    assert [row.model_dump() for row in summary.categories] == [
        # Excedida: lo que queda es negativo (RF-13).
        {
            "category_id": comida.id,
            "name": "Comida",
            "budget": 400_000,
            "spent": 412_000,
            "remaining": -12_000,
        },
        # Sin presupuesto: no hay "lo que queda".
        {
            "category_id": transporte.id,
            "name": "Transporte",
            "budget": None,
            "spent": 38_000,
            "remaining": None,
        },
        # Sin gastos: gastado 0 (RF-12).
        {
            "category_id": ocio.id,
            "name": "Ocio",
            "budget": 100_000,
            "spent": 0,
            "remaining": 100_000,
        },
        # Ni presupuesto ni gastos en el mes: aparece igual (decisión 2).
        {
            "category_id": salud.id,
            "name": "Salud",
            "budget": None,
            "spent": 0,
            "remaining": None,
        },
    ]
    # El total gastado incluye las categorías sin presupuesto (RF-14).
    assert summary.total.model_dump() == {
        "budget": 500_000,
        "spent": 450_000,
        "remaining": 50_000,
    }


def test_summary_without_any_budget_has_no_total_budget(
    session: Session, space: Space, user: User
) -> None:
    # RF-14: sin presupuestos no hay total presupuestado ni total que queda.
    comida = add_category(session, space, "Comida")
    spend(session, comida, user, 20_000, date(2026, 10, 1))

    total = build_summary(session, space.id, "2026-10").total

    assert total.model_dump() == {"budget": None, "spent": 20_000, "remaining": None}


def test_a_removed_budget_counts_as_no_budget_in_the_summary(
    session: Session, space: Space
) -> None:
    comida = add_category(session, space, "Comida")
    set_budget(session, comida, "2026-09", 400_000)
    set_budget(session, comida, "2026-10", None)

    summary = build_summary(session, space.id, "2026-10")

    assert summary.categories[0].budget is None
    assert summary.total.budget is None


def test_summary_of_a_space_without_categories_is_empty(
    session: Session, space: Space
) -> None:
    summary = build_summary(session, space.id, "2026-10")

    assert summary.categories == []
    assert summary.total.model_dump() == {"budget": None, "spent": 0, "remaining": None}


def test_summary_amounts_are_ints(session: Session, space: Space, user: User) -> None:
    # RF-16, principio 6.
    comida = add_category(session, space, "Comida")
    set_budget(session, comida, "2026-10", 400_000)
    spend(session, comida, user, 20_000, date(2026, 10, 1))

    summary = build_summary(session, space.id, "2026-10")
    row, total = summary.categories[0], summary.total

    for value in (row.budget, row.spent, row.remaining, total.budget, total.spent):
        assert type(value) is int


def test_nothing_from_another_space_is_counted(
    session: Session, space: Space, user: User
) -> None:
    # RF-18: ni gastos, ni presupuestos, ni categorías de otro espacio.
    other = Space(name="Viajes")
    session.add(other)
    session.flush()
    comida = add_category(session, space, "Comida")
    foreign = add_category(session, other, "Comida")
    set_budget(session, foreign, "2026-10", 900_000)
    spend(session, foreign, user, 70_000, date(2026, 10, 5))

    assert effective_budgets(session, space.id, date(2026, 10, 1)) == {}
    assert spent_by_category(session, space.id, *OCTOBER) == {}
    summary = build_summary(session, space.id, "2026-10")
    assert [row.category_id for row in summary.categories] == [comida.id]
    assert summary.total.model_dump() == {"budget": None, "spent": 0, "remaining": None}
