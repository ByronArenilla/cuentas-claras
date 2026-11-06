"""Cuotas y deudas de las compras con tarjeta, leídas de la base de datos
(spec 009).

El cálculo vive en `app/installments.py`, sin base de datos; aquí solo se
leen la compra, la tasa de su tarjeta y sus abonos (principio 10). Todas las
consultas filtran por espacio (RF-43).
"""

from dataclasses import dataclass
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import dates
from app.installments import (
    Installment,
    PrepaymentPlan,
    Reduces,
    build_schedule,
    prepayment_limit,
)
from app.models import Card, CardStatement, Expense, Prepayment


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


# --- Deuda de una tarjeta en un mes (RF-34, RF-35) ---

# Máximo de cuotas (decisión 10): una compra con primera cuota más de 47
# meses antes del periodo ya no tiene cuotas en él.
WINDOW_MONTHS = 47


@dataclass(frozen=True)
class CardMonth:
    """Lo que una tarjeta cobra en un mes: las cuotas de sus compras, los
    abonos, y el valor real del extracto si se escribió."""

    card: Card
    # Cada cuota del mes con su compra, en orden de compra.
    installments: list[tuple[Expense, Installment]]
    prepayments: list[tuple[Expense, Prepayment]]
    statement: int | None

    @property
    def estimated(self) -> int:
        """Suma del capital y el interés de las cuotas del mes (RF-34)."""
        return sum(row.amount for _, row in self.installments)

    @property
    def amount(self) -> int:
        """El valor real o, si no hay, lo estimado; más los abonos (RF-35)."""
        base = self.estimated if self.statement is None else self.statement
        return base + sum(prepayment.amount for _, prepayment in self.prepayments)

    @property
    def is_empty(self) -> bool:
        return not self.installments and not self.prepayments and self.statement is None


def window_purchases(
    db: Session, card: Card, first: str, last: str, *, lock: bool = False
) -> list[Expense]:
    """Compras de la tarjeta con primera cuota entre `first - 47` y `last`:
    las únicas que pueden tener cuotas entre `first` y `last`."""
    query = (
        select(Expense)
        .where(
            Expense.card_id == card.id,
            Expense.space_id == card.space_id,
            Expense.first_due_start
            >= dates.period_bounds(dates.shift_period(first, -WINDOW_MONTHS))[0],
            Expense.first_due_start <= dates.period_bounds(last)[0],
        )
        .order_by(Expense.id)
    )
    if lock:
        query = query.with_for_update()
    return list(db.scalars(query))


def prepayments_by_purchase(
    db: Session, purchases: list[Expense]
) -> dict[int, list[Prepayment]]:
    """Abonos de cada compra, en orden de mes, con una sola consulta."""
    found: dict[int, list[Prepayment]] = {purchase.id: [] for purchase in purchases}
    if purchases:
        rows = db.scalars(
            select(Prepayment)
            .where(
                Prepayment.expense_id.in_(found),
                Prepayment.space_id == purchases[0].space_id,
            )
            .order_by(Prepayment.period_start)
        )
        for row in rows:
            found[row.expense_id].append(row)
    return found


def statement_amount(db: Session, card: Card, period: str) -> int | None:
    return db.scalar(
        select(CardStatement.amount).where(
            CardStatement.card_id == card.id,
            CardStatement.space_id == card.space_id,
            CardStatement.period_start == dates.period_bounds(period)[0],
        )
    )


def card_month(db: Session, card: Card, period: str) -> CardMonth:
    """Cuotas, abonos y valor real de la tarjeta en `period` (RF-34 a RF-36)."""
    purchases = window_purchases(db, card, period, period)
    prepayments = prepayments_by_purchase(db, purchases)
    installments = []
    month_prepayments = []
    for purchase in purchases:
        own = prepayments[purchase.id]
        for row in schedule_of(purchase, card.monthly_rate_bp, own):
            if row.period == period:
                installments.append((purchase, row))
        month_prepayments += [
            (purchase, prepayment)
            for prepayment in own
            if dates.period_of(prepayment.period_start) == period
        ]
    return CardMonth(
        card=card,
        installments=installments,
        prepayments=month_prepayments,
        statement=statement_amount(db, card, period),
    )


# --- Pagar todo (RF-29, RF-30) ---


class NothingToPayOff(Exception):
    """Ninguna compra del extracto tiene saldo después de la cuota del mes."""


class LaterPrepayment(Exception):
    """Una compra que habría que saldar ya tiene un abono en ese mes o en uno
    posterior."""

    def __init__(self, purchase: Expense, period: str) -> None:
        super().__init__(period)
        self.purchase = purchase
        self.period = period


def pay_off(db: Session, card: Card, period: str, user_id: int) -> list[Prepayment]:
    """Salda en `period` cada compra de la tarjeta con cuota ese mes y saldo
    después de ella, con un abono por ese saldo (decisión 28). Las compras
    cuya primera cuota es posterior no se tocan (RF-30).

    Todo o nada: si una compra choca, lanza `LaterPrepayment` sin crear
    ningún abono; si no hay nada que saldar, `NothingToPayOff`. No hace
    `commit`: lo hace la ruta. Las compras quedan bloqueadas (`FOR UPDATE`)
    mientras se decide, como en un abono.
    """
    start = dates.period_bounds(period)[0]
    purchases = window_purchases(db, card, period, period, lock=True)
    prepayments = prepayments_by_purchase(db, purchases)
    to_settle: list[tuple[Expense, int]] = []
    for purchase in purchases:
        own = prepayments[purchase.id]
        schedule = schedule_of(purchase, card.monthly_rate_bp, own)
        balance = prepayment_limit(schedule, period)
        if balance is None:
            continue
        if own and own[-1].period_start >= start:
            raise LaterPrepayment(purchase, dates.period_of(own[-1].period_start))
        to_settle.append((purchase, balance))

    if not to_settle:
        raise NothingToPayOff
    created = [
        Prepayment(
            space_id=purchase.space_id,
            expense_id=purchase.id,
            period_start=start,
            amount=balance,
            # Un abono por el saldo completo cancela la compra; el modo da
            # igual y se guarda `term` (plan 009).
            reduces="term",
            created_by=user_id,
        )
        for purchase, balance in to_settle
    ]
    db.add_all(created)
    return created
