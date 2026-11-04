"""Presupuesto vigente y resumen de un periodo (spec 004).

Funciones sin nada de HTTP, que se prueban con una sesión de base de datos
(principio 10). Todas las consultas filtran por `space_id` (RF-18).
"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import dates
from app.models import Budget, Category, Expense
from app.schemas import CategorySummaryOut, SummaryOut, TotalSummaryOut


def effective_budgets(db: Session, space_id: int, start: date) -> dict[int, int | None]:
    """Presupuesto vigente el día `start` de cada categoría con algún cambio
    desde ese periodo o antes (RF-3, RF-4, RF-6).

    Las filas llegan de la más antigua a la más reciente y cada una pisa a la
    anterior de su categoría, así que gana la última. Una categoría sin filas
    no aparece; una cuya última fila es nula aparece con `None`. Las dos
    significan "sin presupuesto".
    """
    rows = db.execute(
        select(Budget.category_id, Budget.amount)
        .where(Budget.space_id == space_id, Budget.starts_on <= start)
        .order_by(Budget.starts_on)
    )
    budgets: dict[int, int | None] = {}
    for category_id, amount in rows:
        budgets[category_id] = amount
    return budgets


def spent_by_category(
    db: Session, space_id: int, start: date, end: date
) -> dict[int, int]:
    """Suma de los gastos de cada categoría con `start <= spent_on < end`,
    la misma regla que el listado de gastos (RF-12; RF-9 de la 003).

    Las categorías sin gastos no aparecen.
    """
    rows = db.execute(
        select(Expense.category_id, func.sum(Expense.amount))
        .where(
            Expense.space_id == space_id,
            Expense.spent_on >= start,
            Expense.spent_on < end,
        )
        .group_by(Expense.category_id)
    )
    # `int()`: en PostgreSQL, `SUM` de un `bigint` llega como `Decimal`
    # (RF-16, principio 6).
    return {category_id: int(total) for category_id, total in rows}


def remaining(budget: int | None, spent: int) -> int | None:
    """Lo que queda, negativo si se excedió; sin presupuesto, nada (RF-13)."""
    return None if budget is None else budget - spent


def build_summary(db: Session, space_id: int, period: str) -> SummaryOut:
    """Resumen del periodo: todas las categorías del espacio en orden de
    creación y los totales (RF-11 a RF-14, decisión 2).

    `period` debe venir ya validado: un texto inválido lanza `ValueError`.
    """
    start, end = dates.period_bounds(period)
    budgets = effective_budgets(db, space_id, start)
    spent = spent_by_category(db, space_id, start, end)
    categories = db.execute(
        select(Category.id, Category.name)
        .where(Category.space_id == space_id)
        .order_by(Category.id)
    )

    rows = []
    for category_id, name in categories:
        budget = budgets.get(category_id)
        category_spent = spent.get(category_id, 0)
        rows.append(
            CategorySummaryOut(
                category_id=category_id,
                name=name,
                budget=budget,
                spent=category_spent,
                remaining=remaining(budget, category_spent),
            )
        )

    # Solo suman los presupuestos que existen; si no hay ninguno, no hay
    # total presupuestado. El gastado suma todo, también lo de categorías
    # sin presupuesto (RF-14).
    set_budgets = [row.budget for row in rows if row.budget is not None]
    total_budget = sum(set_budgets) if set_budgets else None
    total_spent = sum(row.spent for row in rows)
    return SummaryOut(
        period=period,
        categories=rows,
        total=TotalSummaryOut(
            budget=total_budget,
            spent=total_spent,
            remaining=remaining(total_budget, total_spent),
        ),
    )
