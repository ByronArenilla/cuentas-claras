"""Gastos de un espacio: registrar, consultar, listar, editar y borrar (spec 003),
los últimos registrados (spec 006) y el rubro de cada gasto (spec 008).

Un gasto planeado lleva un rubro de su mismo mes y la categoría de ese rubro;
uno no planeado, solo su categoría (decisiones 5, 6 y 13 de la 008).

Las rutas reciben el espacio por `member_space`, nunca consultando por
`space_id` directamente (RF-19; RF-28 y RF-29 de la 001).
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import dates
from app.db import get_db
from app.deps import current_user, member_space, requested_period
from app.models import BudgetItem, Expense, Space, User
from app.routers.categories import usable_category
from app.schemas import EXACTLY_ONE_MESSAGE, ExpenseIn, ExpenseOut, ExpensePatch

router = APIRouter(prefix="/spaces/{space_id}/expenses", tags=["expenses"])

EXPENSE_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Gasto no encontrado.")
UNCONFIRMED_DELETE = HTTPException(
    status.HTTP_400_BAD_REQUEST, "Para borrar el gasto, confirma con confirm=true."
)
ITEM_NOT_IN_SPACE = HTTPException(
    status.HTTP_422_UNPROCESSABLE_CONTENT, "El rubro no existe en este espacio."
)
EXACTLY_ONE = HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, EXACTLY_ONE_MESSAGE)


def item_in_space(db: Session, space_id: int, item_id: int) -> BudgetItem:
    """Rubro del cuerpo, solo si es del espacio. Uno de otro espacio responde
    igual que uno inexistente (RF-18 de la 008), como la categoría."""
    item = db.scalar(
        select(BudgetItem).where(
            BudgetItem.id == item_id, BudgetItem.space_id == space_id
        )
    )
    if item is None:
        raise ITEM_NOT_IN_SPACE
    return item


def check_same_month(item: BudgetItem, spent_on: date) -> None:
    """Un gasto solo va en un rubro de su mismo mes (RF-19, decisión 6)."""
    item_period = dates.period_of(item.period_start)
    expense_period = dates.period_of(spent_on)
    if item_period != expense_period:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"El rubro «{item.name}» es de {item_period} y el gasto es de "
            f"{expense_period}. Elige un rubro de {expense_period} o regístralo "
            "como no planeado.",
        )


def commit_or_missing_item(db: Session) -> None:
    """Guarda; si otro miembro borró el rubro entre la comprobación y el
    guardado, la clave foránea frena el gasto y se responde como rubro
    inexistente, no como un error 500 (plan 008, riesgos)."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ITEM_NOT_IN_SPACE from None


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
    (RF-1). El espacio y el autor nunca salen del cuerpo (RF-14).

    Con rubro, la categoría es la del rubro, aunque esté eliminada (RF-20,
    RF-42 de la 008). Sin rubro, la categoría debe ser del espacio (RF-5) y
    estar activa (RF-41 de la 008). La base de datos no lo garantiza: haría
    falta una clave foránea compuesta que cambia la tabla `categories`
    (plan 003).
    """
    if data.budget_item_id is not None:
        item = item_in_space(db, space.id, data.budget_item_id)
        check_same_month(item, data.spent_on)
        category_id = item.category_id
    else:
        category_id = usable_category(db, space.id, data.category_id).id

    expense = Expense(
        **data.model_dump(exclude={"category_id"}),
        category_id=category_id,
        space_id=space.id,
        created_by=user.id,
    )
    db.add(expense)
    commit_or_missing_item(db)
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


def item_changes(db: Session, expense: Expense, changes: dict) -> dict:
    """Rubro y categoría que tendrá el gasto tras la edición, con las reglas
    del plan 008 ("Editar un gasto"). Valida todo antes de que la ruta
    escriba nada (RF-19, RF-21, RF-41).
    """
    spent_on = changes.get("spent_on", expense.spent_on)

    if "budget_item_id" in changes and changes["budget_item_id"] is not None:
        # 1 y 2: ligarlo a un rubro. Con categoría a la vez, se rechaza.
        if "category_id" in changes:
            raise EXACTLY_ONE
        item = item_in_space(db, expense.space_id, changes["budget_item_id"])
        check_same_month(item, spent_on)
        return {"category_id": item.category_id}

    if "budget_item_id" in changes:
        # 3: quitarle el rubro. Queda con la categoría enviada o la que tenía.
        if "category_id" in changes:
            usable_category(db, expense.space_id, changes["category_id"])
        return {}

    if expense.budget_item_id is not None:
        item = db.get_one(BudgetItem, expense.budget_item_id)
        # 4: la categoría de un gasto planeado es la de su rubro.
        if "category_id" in changes:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"El gasto está en el rubro «{item.name}» y usa su categoría. "
                "Para cambiarla, quítale el rubro.",
            )
        # 5: cambiar la fecha no puede sacarlo del mes de su rubro.
        check_same_month(item, spent_on)
        return {}

    if "category_id" in changes:
        usable_category(db, expense.space_id, changes["category_id"])
    return {}


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
    changes.update(item_changes(db, expense, changes))

    for field, value in changes.items():
        setattr(expense, field, value)
    commit_or_missing_item(db)
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
