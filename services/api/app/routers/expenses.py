"""Gastos de un espacio: registrar, consultar, listar, editar y borrar (spec 003),
y los últimos registrados (spec 006).

Las rutas reciben el espacio por `member_space`, nunca consultando por
`space_id` directamente (RF-19; RF-28 y RF-29 de la 001).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import dates
from app.db import get_db
from app.deps import current_user, member_space, requested_period
from app.models import Expense, Space, User
from app.routers.categories import usable_category
from app.schemas import ExpenseIn, ExpenseOut, ExpensePatch

router = APIRouter(prefix="/spaces/{space_id}/expenses", tags=["expenses"])

EXPENSE_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Gasto no encontrado.")
UNCONFIRMED_DELETE = HTTPException(
    status.HTTP_400_BAD_REQUEST, "Para borrar el gasto, confirma con confirm=true."
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


@router.post("", status_code=status.HTTP_201_CREATED)
def create_expense(
    data: ExpenseIn,
    space: Annotated[Space, Depends(member_space)],
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ExpenseOut:
    """Registra un gasto en el espacio de la ruta, a nombre de quien llama
    (RF-1). El espacio y el autor nunca salen del cuerpo (RF-14)."""
    # La categoría debe ser del espacio (RF-5) y estar activa (RF-41 de la
    # 008). La base de datos no lo garantiza: haría falta una clave foránea
    # compuesta que cambia la tabla `categories` (plan 003).
    usable_category(db, space.id, data.category_id)

    expense = Expense(**data.model_dump(), space_id=space.id, created_by=user.id)
    db.add(expense)
    db.commit()
    return ExpenseOut.model_validate(expense)


@router.get("")
def list_expenses(
    space: Annotated[Space, Depends(member_space)],
    db: Annotated[Session, Depends(get_db)],
    period: Annotated[str, Depends(requested_period)],
) -> list[ExpenseOut]:
    """Gastos del espacio en el periodo `YYYY-MM`, por defecto el actual en
    `TZ` (RF-9, RF-10). Del día más reciente al más antiguo y, a igual día,
    del registrado después al registrado antes (decisión 5)."""
    # `requested_period` ya validó el periodo o puso el actual.
    start, end = dates.period_bounds(period)

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


# Antes que `/{expense_id}`: Starlette prueba las rutas en orden y, si no,
# tomaría `recent` como identificador de un gasto (plan 006).
@router.get("/recent")
def recent_expenses(
    space: Annotated[Space, Depends(member_space)],
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
    mine: bool = False,
) -> list[ExpenseOut]:
    """Últimos gastos registrados en el espacio, de cualquier periodo, del
    registrado más recientemente al más antiguo (RF-1 de la 006). Con
    `mine=true`, solo los de quien llama (RF-2 de la 006)."""
    query = select(Expense).where(Expense.space_id == space.id)
    if mine:
        query = query.where(Expense.created_by == user.id)
    expenses = db.scalars(
        query.order_by(Expense.created_at.desc(), Expense.id.desc()).limit(limit)
    )
    return [ExpenseOut.model_validate(expense) for expense in expenses]


@router.get("/{expense_id}")
def read_expense(expense: Annotated[Expense, Depends(space_expense)]) -> ExpenseOut:
    """Un gasto del espacio con todos sus campos, incluido su autor (RF-8)."""
    return ExpenseOut.model_validate(expense)


@router.patch("/{expense_id}")
def update_expense(
    data: ExpensePatch,
    expense: Annotated[Expense, Depends(space_expense)],
    db: Annotated[Session, Depends(get_db)],
) -> ExpenseOut:
    """Cambia solo los campos enviados, con las mismas validaciones que al
    registrar (RF-13). Cualquier miembro puede, aunque lo registrara otro
    (RF-15). `ExpensePatch` no tiene `space_id` ni `created_by` (RF-14)."""
    # `exclude_unset`: solo lo que llegó en el cuerpo (`model_fields_set`).
    # Un `"description": null` sí está y la quita (decisión 8).
    changes = data.model_dump(exclude_unset=True)
    if "category_id" in changes:
        usable_category(db, expense.space_id, changes["category_id"])

    for field, value in changes.items():
        setattr(expense, field, value)
    db.commit()
    return ExpenseOut.model_validate(expense)


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(
    expense: Annotated[Expense, Depends(space_expense)],
    db: Annotated[Session, Depends(get_db)],
    confirm: str | None = None,
) -> Response:
    """Borra el gasto de forma definitiva, solo con `confirm=true` (RF-16,
    RF-17). Cualquier miembro puede, aunque lo registrara otro (RF-15).

    Se exige el texto `true` exacto, no cualquier valor que FastAPI leería
    como verdadero (`1`, `yes`, `on`): la confirmación debe ser explícita
    (principio 8, decisión 3).
    """
    if confirm != "true":
        raise UNCONFIRMED_DELETE

    # Por `id` y `space_id`: la sentencia nunca toca otra fila (RF-18).
    db.execute(
        delete(Expense).where(
            Expense.id == expense.id, Expense.space_id == expense.space_id
        )
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
