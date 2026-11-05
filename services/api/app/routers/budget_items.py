"""Rubros del plan de un mes: crear, editar y borrar (spec 008, RF-1 a RF-9).

Las rutas reciben el espacio por `member_space`, nunca consultando por
`space_id` directamente (RF-28; RF-28 y RF-29 de la 001). No hay ruta para
leer los rubros: los trae el resumen del mes (plan 008).
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import dates
from app.db import get_db
from app.deps import member_space
from app.models import BudgetItem, Expense, Space
from app.plan import stored_name
from app.routers.categories import usable_category
from app.schemas import BudgetItemIn, BudgetItemOut, BudgetItemPatch

router = APIRouter(prefix="/spaces/{space_id}/budget-items", tags=["budget-items"])

ITEM_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Rubro no encontrado.")


def duplicate(name: str, period_start: date) -> HTTPException:
    # Nombra el rubro que ya existe, con su escritura: así se entiende por qué
    # "accion" choca con "Acción" (RF-3).
    return HTTPException(
        status.HTTP_409_CONFLICT,
        f"Ya existe el rubro «{name}» en {dates.period_of(period_start)}.",
    )


def space_item(
    item_id: int,
    space: Annotated[Space, Depends(member_space)],
    db: Annotated[Session, Depends(get_db)],
) -> BudgetItem:
    """Rubro de la ruta, solo si es del espacio que ya validó `member_space`.

    Se busca por `id` **y** `space_id`: uno de otro espacio responde igual que
    uno inexistente, aunque quien llama sea miembro de los dos (RF-9).
    """
    item = db.scalar(
        select(BudgetItem).where(
            BudgetItem.id == item_id, BudgetItem.space_id == space.id
        )
    )
    if item is None:
        raise ITEM_NOT_FOUND
    return item


def commit_or_duplicate(db: Session, item: BudgetItem, name: str) -> None:
    """Guarda; si el índice único frena el nombre (otra petición lo usó a la
    vez), deshace todo y responde como un nombre repetido (RF-3)."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        stored = stored_name(db, BudgetItem, item.space_id, item.period_start, name)
        raise duplicate(stored or name, item.period_start) from None


@router.post("", status_code=status.HTTP_201_CREATED)
def create_budget_item(
    data: BudgetItemIn,
    space: Annotated[Space, Depends(member_space)],
    db: Annotated[Session, Depends(get_db)],
) -> BudgetItemOut:
    """Crea un rubro en el mes `period`; cualquier miembro puede (RF-1). La
    categoría debe ser del espacio y estar activa (RF-5, RF-41)."""
    usable_category(db, space.id, data.category_id)
    # El día 1 del mes: `period` ya viene validado por `BudgetItemIn`.
    period_start, _ = dates.period_bounds(data.period)
    if stored := stored_name(db, BudgetItem, space.id, period_start, data.name):
        raise duplicate(stored, period_start)

    item = BudgetItem(
        space_id=space.id,
        period_start=period_start,
        name=data.name,
        category_id=data.category_id,
        amount=data.amount,
    )
    db.add(item)
    commit_or_duplicate(db, item, data.name)
    return BudgetItemOut.model_validate(item)


@router.patch("/{item_id}")
def update_budget_item(
    data: BudgetItemPatch,
    item: Annotated[BudgetItem, Depends(space_item)],
    db: Annotated[Session, Depends(get_db)],
) -> BudgetItemOut:
    """Cambia solo el nombre, la categoría o el monto enviados (RF-6). El mes
    no se cambia (decisión 12).

    Con una categoría nueva, sus gastos pasan a ella en la misma transacción
    (RF-7). Reenviar la categoría que ya tiene no la comprueba otra vez: un
    rubro cuya categoría se eliminó sigue editándose (RF-42).
    """
    changes = data.model_dump(exclude_unset=True)
    # Primero se valida todo; después se escribe.
    if "name" in changes and (
        stored := stored_name(
            db,
            BudgetItem,
            item.space_id,
            item.period_start,
            changes["name"],
            exclude_id=item.id,
        )
    ):
        raise duplicate(stored, item.period_start)
    new_category = changes.get("category_id", item.category_id)
    if new_category != item.category_id:
        usable_category(db, item.space_id, new_category)
        # Por `budget_item_id` y `space_id`: nunca toca gastos de otro espacio.
        db.execute(
            update(Expense)
            .where(
                Expense.budget_item_id == item.id,
                Expense.space_id == item.space_id,
            )
            .values(category_id=new_category)
        )

    for field, value in changes.items():
        setattr(item, field, value)
    commit_or_duplicate(db, item, item.name)
    return BudgetItemOut.model_validate(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget_item(
    item: Annotated[BudgetItem, Depends(space_item)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Borra el rubro sin pedir confirmación. Sus gastos no se borran: quedan
    no planeados, con la categoría que tenía el rubro, que ya era la suya
    (RF-8, decisión 8)."""
    db.execute(
        update(Expense)
        .where(
            Expense.budget_item_id == item.id,
            Expense.space_id == item.space_id,
        )
        .values(budget_item_id=None)
    )
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
