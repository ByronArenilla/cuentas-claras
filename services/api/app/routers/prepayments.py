"""Plan de cuotas de una compra con tarjeta y sus abonos (spec 009, RF-21 a
RF-30).

Las rutas reciben el gasto por `space_expense`, que pasa por `member_space`
(RF-42).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.debts import purchase_prepayments, purchase_schedule
from app.models import Expense
from app.routers.expenses import space_expense
from app.schemas import InstallmentOut, PrepaymentOut, ScheduleOut

router = APIRouter(prefix="/spaces/{space_id}/expenses", tags=["prepayments"])

NOT_A_CARD_PURCHASE = HTTPException(
    status.HTTP_404_NOT_FOUND,
    "Este gasto no es una compra con tarjeta; no tiene cuotas.",
)


def schedule_out(db: Session, expense: Expense) -> ScheduleOut:
    assert expense.card_id is not None
    return ScheduleOut(
        expense_id=expense.id,
        card_id=expense.card_id,
        installments=[InstallmentOut.of(row) for row in purchase_schedule(db, expense)],
        prepayments=[
            PrepaymentOut.model_validate(row)
            for row in purchase_prepayments(db, expense)
        ],
    )


@router.get("/{expense_id}/installments")
def read_schedule(
    expense: Annotated[Expense, Depends(space_expense)],
    db: Annotated[Session, Depends(get_db)],
) -> ScheduleOut:
    """Plan de cuotas de la compra: cada cuota con su mes, capital, interés y
    saldo, y sus abonos (RF-21). Un gasto sin tarjeta no tiene cuotas: el
    gasto existe, pero su plan no, así que responde `404`."""
    if expense.card_id is None:
        raise NOT_A_CARD_PURCHASE
    return schedule_out(db, expense)
