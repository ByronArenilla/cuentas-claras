"""Resumen del plan de un mes (spec 008, RF-23 a RF-25; reemplaza al de la 004),
con las deudas de las tarjetas (spec 009, RF-36 a RF-39).

Las compras con tarjeta no cuentan en su rubro ni en su categoría: cuentan
como Deudas en los meses en que se pagan sus cuotas (decisiones 1 y 6 de la
009).

Funciones sin nada de HTTP, que se prueban con una sesión de base de datos
(principio 10). Todas las consultas filtran por `space_id` (RF-29).
"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import dates
from app.debts import card_debts
from app.models import BudgetItem, Category, Expense, Income
from app.schemas import (
    CategorySummaryOut,
    IncomeSummaryOut,
    ItemSummaryOut,
    SummaryOut,
    TotalSummaryOut,
)


def spent_by_category(
    db: Session, space_id: int, start: date, end: date
) -> dict[int, int]:
    """Suma de los gastos de cada categoría con `start <= spent_on < end`,
    planeados o no, con la regla de periodo de la 003 (RF-9 de la 003).

    Las categorías sin gastos no aparecen. Las compras con tarjeta no cuentan:
    van a Deudas (RF-37 de la 009). Un gasto a crédito sin tarjeta, de antes
    de la 009, sí cuenta el día del gasto.
    """
    rows = db.execute(
        select(Expense.category_id, func.sum(Expense.amount))
        .where(
            Expense.space_id == space_id,
            Expense.card_id.is_(None),
            Expense.spent_on >= start,
            Expense.spent_on < end,
        )
        .group_by(Expense.category_id)
    )
    # `int()`: en PostgreSQL, `SUM` de un `bigint` llega como `Decimal`
    # (RF-24, principio 6).
    return {category_id: int(total) for category_id, total in rows}


def spent_by_item(db: Session, space_id: int, start: date, end: date) -> dict[int, int]:
    """Suma de los gastos de cada rubro en el periodo. Los gastos no
    planeados no cuentan; los rubros sin gastos no aparecen."""
    rows = db.execute(
        select(Expense.budget_item_id, func.sum(Expense.amount))
        .where(
            Expense.space_id == space_id,
            Expense.budget_item_id.is_not(None),
            Expense.spent_on >= start,
            Expense.spent_on < end,
        )
        .group_by(Expense.budget_item_id)
    )
    return {item_id: int(total) for item_id, total in rows}


def build_summary(db: Session, space_id: int, period: str) -> SummaryOut:
    """Resumen del periodo: ingresos, rubros, categorías y totales (RF-23).

    Un mes sin plan sale con listas vacías y montos en 0, sin crear nada
    (RF-25). `period` debe venir ya validado: un texto inválido lanza
    `ValueError`.
    """
    start, end = dates.period_bounds(period)
    spent_items = spent_by_item(db, space_id, start, end)
    spent_categories = spent_by_category(db, space_id, start, end)

    incomes = [
        IncomeSummaryOut(id=income.id, name=income.name, amount=income.amount)
        for income in db.scalars(
            select(Income)
            .where(Income.space_id == space_id, Income.period_start == start)
            .order_by(Income.id)
        )
    ]
    items = [
        ItemSummaryOut(
            id=item.id,
            name=item.name,
            category_id=item.category_id,
            planned=item.amount,
            spent=spent_items.get(item.id, 0),
            remaining=item.amount - spent_items.get(item.id, 0),
        )
        for item in db.scalars(
            select(BudgetItem)
            .where(BudgetItem.space_id == space_id, BudgetItem.period_start == start)
            .order_by(BudgetItem.id)
        )
    ]

    planned_categories: dict[int, int] = {}
    for item in items:
        planned_categories[item.category_id] = (
            planned_categories.get(item.category_id, 0) + item.planned
        )

    categories = []
    for category in db.scalars(
        select(Category).where(Category.space_id == space_id).order_by(Category.id)
    ):
        planned = planned_categories.get(category.id, 0)
        spent = spent_categories.get(category.id, 0)
        deleted = category.deleted_at is not None
        # Una eliminada solo sale si tiene rubros o gastos en el mes, así los
        # totales por categoría cuadran sin llenar la lista (decisión 18).
        if deleted and category.id not in planned_categories and not spent:
            continue
        categories.append(
            CategorySummaryOut(
                category_id=category.id,
                name=category.name,
                planned=planned,
                spent=spent,
                deleted=deleted,
            )
        )

    debts = card_debts(db, space_id, period)
    debt_total = sum(row.amount for row in debts)

    income = sum(row.amount for row in incomes)
    # La deuda del mes cuenta sola en lo planeado y en lo gastado (decisión 3
    # de la 009, RF-38).
    planned = sum(row.planned for row in items) + debt_total
    spent_planned = sum(spent_items.values())
    spent_own_day = sum(spent_categories.values())
    spent = spent_own_day + debt_total
    return SummaryOut(
        period=period,
        incomes=incomes,
        budget_items=items,
        categories=categories,
        debts=debts,
        total=TotalSummaryOut(
            income=income,
            planned=planned,
            debts=debt_total,
            spent_planned=spent_planned,
            spent_unplanned=spent_own_day - spent_planned,
            spent=spent,
            unassigned=income - planned,
            balance=income - spent,
        ),
    )
