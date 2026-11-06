"""Cuotas y deudas de las compras con tarjeta, leídas de la base de datos
(spec 009).

El cálculo vive en `app/installments.py`, sin base de datos; aquí solo se
leen la compra, la tasa de su tarjeta y sus abonos (principio 10). Todas las
consultas filtran por espacio (RF-43).
"""

from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import dates
from app.installments import Installment, PrepaymentPlan, Reduces, build_schedule
from app.models import Card, Expense, Prepayment


def purchase_prepayments(db: Session, expense: Expense) -> list[Prepayment]:
    """Abonos de la compra, en orden de mes."""
    return list(
        db.scalars(
            select(Prepayment)
            .where(
                Prepayment.expense_id == expense.id,
                Prepayment.space_id == expense.space_id,
            )
            .order_by(Prepayment.period_start)
        )
    )


def schedule_of(
    expense: Expense, rate_bp: int | None, prepayments: list[Prepayment]
) -> list[Installment]:
    """Cuotas de una compra con tarjeta ya leída (RF-19 a RF-26)."""
    assert expense.installments is not None and expense.first_due_start is not None
    return build_schedule(
        expense.amount,
        expense.installments,
        rate_bp,
        dates.period_of(expense.first_due_start),
        [
            PrepaymentPlan(
                dates.period_of(prepayment.period_start),
                prepayment.amount,
                # La CHECK de la tabla garantiza que es uno de los dos modos.
                cast(Reduces, prepayment.reduces),
            )
            for prepayment in prepayments
        ],
    )


def purchase_schedule(db: Session, expense: Expense) -> list[Installment]:
    """Cuotas de una compra con tarjeta, con la tasa actual de su tarjeta
    (decisión 14) y sus abonos (RF-21)."""
    card = db.get_one(Card, expense.card_id)
    return schedule_of(expense, card.monthly_rate_bp, purchase_prepayments(db, expense))
