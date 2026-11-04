"""Gastos de un espacio: registrar, consultar, listar, editar y borrar (spec 003).

Las rutas reciben el espacio por `member_space`, nunca consultando por
`space_id` directamente (RF-19; RF-28 y RF-29 de la 001).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user, member_space
from app.models import Category, Expense, Space, User
from app.schemas import ExpenseIn, ExpenseOut

router = APIRouter(prefix="/spaces/{space_id}/expenses", tags=["expenses"])

CATEGORY_NOT_IN_SPACE = HTTPException(
    status.HTTP_422_UNPROCESSABLE_CONTENT, "La categoría no existe en este espacio."
)


def check_category(db: Session, space_id: int, category_id: int) -> None:
    """Exige que la categoría sea del espacio (RF-5).

    Se busca por `id` y `space_id` a la vez, así que una categoría de otro
    espacio y una inexistente reciben el mismo mensaje. La base de datos no lo
    garantiza: haría falta una clave foránea compuesta que cambia la tabla
    `categories` (plan 003).
    """
    found = db.scalar(
        select(Category.id).where(
            Category.id == category_id, Category.space_id == space_id
        )
    )
    if found is None:
        raise CATEGORY_NOT_IN_SPACE


@router.post("", status_code=status.HTTP_201_CREATED)
def create_expense(
    data: ExpenseIn,
    space: Annotated[Space, Depends(member_space)],
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ExpenseOut:
    """Registra un gasto en el espacio de la ruta, a nombre de quien llama
    (RF-1). El espacio y el autor nunca salen del cuerpo (RF-14)."""
    check_category(db, space.id, data.category_id)

    expense = Expense(**data.model_dump(), space_id=space.id, created_by=user.id)
    db.add(expense)
    db.commit()
    return ExpenseOut.model_validate(expense)
