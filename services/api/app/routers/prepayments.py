"""Plan de cuotas de una compra con tarjeta y sus abonos (spec 009, RF-21 a
RF-30).

Las rutas reciben el gasto por `space_expense`, que pasa por `member_space`
(RF-42).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import dates
from app.db import get_db
from app.debts import purchase_prepayments, purchase_schedule
from app.deps import current_user
from app.installments import Installment, prepayment_limit
from app.models import Expense, Prepayment, User
from app.routers.expenses import space_expense
from app.schemas import (
    InstallmentOut,
    PrepaymentCreatedOut,
    PrepaymentIn,
    PrepaymentOut,
    ScheduleOut,
    format_pesos,
)

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


def later_prepayment(period: str) -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        f"La compra ya tiene un abono en {period}; un abono nuevo debe ser de un "
        "mes posterior.",
    )


def months_message(schedule: list[Installment], after: str | None) -> str:
    """Meses en que se puede abonar: los que tienen cuota y saldo después, y
    son posteriores al último abono (RF-23, decisión 18)."""
    valid = [
        row.period
        for row in schedule
        if row.balance_after and (after is None or row.period > after)
    ]
    first, last = schedule[0].period, schedule[-1].period
    if not valid:
        return (
            f"La compra tiene cuotas de {first} a {last} y no le queda saldo para "
            "abonar."
        )
    return (
        f"La compra tiene cuotas de {first} a {last} y queda saldo después de las "
        f"de {valid[0]} a {valid[-1]}; elige uno de esos meses."
    )


@router.post("/{expense_id}/prepayments", status_code=status.HTTP_201_CREATED)
def create_prepayment(
    data: PrepaymentIn,
    expense: Annotated[Expense, Depends(space_expense)],
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PrepaymentCreatedOut:
    """Abona a una compra con tarjeta en un mes, bajando la cuota o el plazo
    (RF-22 a RF-26). Nunca cambia la compra (RF-28).

    La compra se bloquea (`FOR UPDATE`) mientras se decide: en PostgreSQL,
    dos abonos a la vez de meses distintos no pueden pasar los dos la
    comprobación de "posterior al último" (plan 009). En SQLite no hace
    nada, pero SQLite ya escribe de a una transacción.
    """
    if expense.card_id is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Solo se abona a una compra con tarjeta.",
        )
    db.execute(select(Expense.id).where(Expense.id == expense.id).with_for_update())

    previous = purchase_prepayments(db, expense)
    last = dates.period_of(previous[-1].period_start) if previous else None
    if last is not None and data.period <= last:
        raise later_prepayment(last)

    schedule = purchase_schedule(db, expense)
    limit = prepayment_limit(schedule, data.period)
    if limit is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, months_message(schedule, last)
        )
    if data.amount > limit:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"El saldo de la compra después de la cuota de {data.period} es "
            f"{format_pesos(limit)}; el abono no puede pasar de ahí.",
        )

    prepayment = Prepayment(
        space_id=expense.space_id,
        expense_id=expense.id,
        period_start=dates.period_bounds(data.period)[0],
        amount=data.amount,
        reduces=data.reduces,
        created_by=user.id,
    )
    db.add(prepayment)
    try:
        db.commit()
    except IntegrityError:
        # Otro abono del mismo mes entró entre la comprobación y el guardado.
        db.rollback()
        raise later_prepayment(data.period) from None
    return PrepaymentCreatedOut(
        prepayment=PrepaymentOut.model_validate(prepayment),
        schedule=schedule_out(db, expense),
    )


@router.delete(
    "/{expense_id}/prepayments/{prepayment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_prepayment(
    prepayment_id: int,
    expense: Annotated[Expense, Depends(space_expense)],
    db: Annotated[Session, Depends(get_db)],
    confirm: str | None = None,
) -> Response:
    """Borra un abono solo con `confirm=true`, como un gasto: es plata que
    salió (RF-27, decisión 18). Las cuotas de la compra se recalculan solas
    al leerlas."""
    if confirm != "true":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Para borrar el abono, confirma con confirm=true.",
        )
    prepayment = db.scalar(
        select(Prepayment).where(
            Prepayment.id == prepayment_id,
            Prepayment.expense_id == expense.id,
            Prepayment.space_id == expense.space_id,
        )
    )
    if prepayment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Abono no encontrado.")
    db.delete(prepayment)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
