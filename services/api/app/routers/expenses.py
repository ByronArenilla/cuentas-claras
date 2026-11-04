"""Gastos de un espacio: registrar, consultar, listar, editar y borrar (spec 003).

Las rutas reciben el espacio por `member_space`, nunca consultando por
`space_id` directamente (RF-19; RF-28 y RF-29 de la 001).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import dates
from app.db import get_db
from app.deps import current_user, member_space
from app.models import Category, Expense, Space, User
from app.schemas import ExpenseIn, ExpenseOut

router = APIRouter(prefix="/spaces/{space_id}/expenses", tags=["expenses"])

CATEGORY_NOT_IN_SPACE = HTTPException(
    status.HTTP_422_UNPROCESSABLE_CONTENT, "La categoría no existe en este espacio."
)
EXPENSE_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Gasto no encontrado.")
INVALID_PERIOD = HTTPException(
    status.HTTP_422_UNPROCESSABLE_CONTENT,
    "El periodo debe tener el formato AAAA-MM, por ejemplo 2026-10.",
)


def space_expense(
    expense_id: int,
    space: Annotated[Space, Depends(member_space)],
    db: Annotated[Session, Depends(get_db)],
) -> Expense:
    """Gasto de la ruta, solo si es del espacio que ya validó `member_space`.

    Se busca por `id` **y** `space_id`: un gasto de otro espacio responde
    igual que uno inexistente, aunque quien llama sea miembro de los dos
    (RF-12).
    """
    expense = db.scalar(
        select(Expense).where(Expense.id == expense_id, Expense.space_id == space.id)
    )
    if expense is None:
        raise EXPENSE_NOT_FOUND
    return expense


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


@router.get("")
def list_expenses(
    space: Annotated[Space, Depends(member_space)],
    db: Annotated[Session, Depends(get_db)],
    period: str | None = None,
) -> list[ExpenseOut]:
    """Gastos del espacio en el periodo `YYYY-MM`, por defecto el actual en
    `TZ` (RF-9, RF-10). Del día más reciente al más antiguo y, a igual día,
    del registrado después al registrado antes (decisión 5)."""
    if period is None:
        period = dates.period_of(dates.today())
    try:
        start, end = dates.period_bounds(period)
    except ValueError:
        raise INVALID_PERIOD from None

    expenses = db.scalars(
        select(Expense)
        .where(
            Expense.space_id == space.id,
            Expense.spent_on >= start,
            Expense.spent_on < end,
        )
        .order_by(Expense.spent_on.desc(), Expense.id.desc())
    )
    return [ExpenseOut.model_validate(expense) for expense in expenses]


@router.get("/{expense_id}")
def read_expense(expense: Annotated[Expense, Depends(space_expense)]) -> ExpenseOut:
    """Un gasto del espacio con todos sus campos, incluido su autor (RF-8)."""
    return ExpenseOut.model_validate(expense)
