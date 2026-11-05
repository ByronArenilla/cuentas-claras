"""Ingresos del plan de un mes: crear, editar y borrar (spec 008, RF-10 a
RF-12).

Las rutas reciben el espacio por `member_space`, nunca consultando por
`space_id` directamente (RF-28). No hay ruta para leer los ingresos: los trae
el resumen del mes (plan 008).
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import dates
from app.db import get_db
from app.deps import member_space
from app.models import Income, Space
from app.plan import stored_name
from app.schemas import IncomeIn, IncomeOut, IncomePatch

router = APIRouter(prefix="/spaces/{space_id}/incomes", tags=["incomes"])

INCOME_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Ingreso no encontrado.")


def duplicate(name: str, period_start: date) -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        f"Ya existe el ingreso «{name}» en {dates.period_of(period_start)}.",
    )


def space_income(
    income_id: int,
    space: Annotated[Space, Depends(member_space)],
    db: Annotated[Session, Depends(get_db)],
) -> Income:
    """Ingreso de la ruta, solo si es del espacio que ya validó `member_space`
    (RF-12): uno de otro espacio responde igual que uno inexistente."""
    income = db.scalar(
        select(Income).where(Income.id == income_id, Income.space_id == space.id)
    )
    if income is None:
        raise INCOME_NOT_FOUND
    return income


def commit_or_duplicate(db: Session, income: Income, name: str) -> None:
    """Guarda; si el índice único frena el nombre (otra petición lo usó a la
    vez), deshace todo y responde como un nombre repetido."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        stored = stored_name(db, Income, income.space_id, income.period_start, name)
        raise duplicate(stored or name, income.period_start) from None


@router.post("", status_code=status.HTTP_201_CREATED)
def create_income(
    data: IncomeIn,
    space: Annotated[Space, Depends(member_space)],
    db: Annotated[Session, Depends(get_db)],
) -> IncomeOut:
    """Crea un ingreso en el mes `period`; cualquier miembro puede (RF-10)."""
    period_start, _ = dates.period_bounds(data.period)
    if stored := stored_name(db, Income, space.id, period_start, data.name):
        raise duplicate(stored, period_start)

    income = Income(
        space_id=space.id,
        period_start=period_start,
        name=data.name,
        amount=data.amount,
    )
    db.add(income)
    commit_or_duplicate(db, income, data.name)
    return IncomeOut.model_validate(income)


@router.patch("/{income_id}")
def update_income(
    data: IncomePatch,
    income: Annotated[Income, Depends(space_income)],
    db: Annotated[Session, Depends(get_db)],
) -> IncomeOut:
    """Cambia solo el nombre o el monto enviados; el mes no se cambia (RF-11)."""
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes and (
        stored := stored_name(
            db,
            Income,
            income.space_id,
            income.period_start,
            changes["name"],
            exclude_id=income.id,
        )
    ):
        raise duplicate(stored, income.period_start)

    for field, value in changes.items():
        setattr(income, field, value)
    commit_or_duplicate(db, income, income.name)
    return IncomeOut.model_validate(income)


@router.delete("/{income_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_income(
    income: Annotated[Income, Depends(space_income)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Borra el ingreso sin pedir confirmación: no toca ningún gasto (RF-11)."""
    db.delete(income)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
