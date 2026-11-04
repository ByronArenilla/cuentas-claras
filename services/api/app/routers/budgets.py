"""Presupuesto de un espacio: fijarlo o quitarlo desde un periodo (spec 004).

Las rutas reciben el espacio por `member_space`, nunca consultando por
`space_id` directamente (RF-17; RF-28 y RF-29 de la 001).
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import dates
from app.db import get_db
from app.deps import member_space
from app.models import Budget, Category, Space
from app.schemas import BudgetIn, BudgetOut

router = APIRouter(prefix="/spaces/{space_id}", tags=["budgets"])

CATEGORY_NOT_FOUND = HTTPException(
    status.HTTP_404_NOT_FOUND, "Categoría no encontrada."
)


def space_category(
    category_id: int,
    space: Annotated[Space, Depends(member_space)],
    db: Annotated[Session, Depends(get_db)],
) -> Category:
    """Categoría de la ruta, solo si es del espacio que ya validó `member_space`.

    Se busca por `id` **y** `space_id`: una de otro espacio responde igual que
    una inexistente, aunque quien llama sea miembro de los dos (RF-9). Es
    `404` y no `422` como al registrar un gasto porque la categoría va en la
    ruta, no en el cuerpo (plan 004).
    """
    category = db.scalar(
        select(Category).where(
            Category.id == category_id, Category.space_id == space.id
        )
    )
    if category is None:
        raise CATEGORY_NOT_FOUND
    return category


def find_budget(
    db: Session, space_id: int, category_id: int, starts_on: date
) -> Budget | None:
    """La fila de esa categoría desde ese periodo, si ya existe."""
    return db.scalar(
        select(Budget).where(
            Budget.space_id == space_id,
            Budget.category_id == category_id,
            Budget.starts_on == starts_on,
        )
    )


def save_budget(
    db: Session, space_id: int, category_id: int, starts_on: date, amount: int | None
) -> None:
    """Actualiza la fila de ese periodo o, si no existe, la crea (RF-5)."""
    budget = find_budget(db, space_id, category_id, starts_on)
    if budget is None:
        db.add(
            Budget(
                space_id=space_id,
                category_id=category_id,
                starts_on=starts_on,
                amount=amount,
            )
        )
    else:
        budget.amount = amount
    db.commit()


@router.put("/budgets/{category_id}")
def set_budget(
    data: BudgetIn,
    category: Annotated[Category, Depends(space_category)],
    db: Annotated[Session, Depends(get_db)],
) -> BudgetOut:
    """Fija el presupuesto de la categoría desde `period`, o lo quita con
    `"amount": null` (RF-1, RF-6). Rige hasta el siguiente cambio de la
    categoría y no toca los periodos anteriores (RF-3, RF-4). Cualquier
    miembro puede (decisión 5); quitarlo no pide confirmación (decisión 4).
    """
    # El día 1 del periodo: `period` ya viene validado por `BudgetIn`.
    starts_on, _ = dates.period_bounds(data.period)
    try:
        save_budget(db, category.space_id, category.id, starts_on, data.amount)
    except IntegrityError:
        # Otra petición creó la misma fila entre la búsqueda y el guardado:
        # el índice único frena esta, y tras el rollback la fila ya existe y
        # se actualiza. Gana la última, como en cualquier `PUT` (RF-5).
        db.rollback()
        save_budget(db, category.space_id, category.id, starts_on, data.amount)
    return BudgetOut(category_id=category.id, period=data.period, amount=data.amount)
