"""Plan del mes: rubros e ingresos (spec 008).

Funciones sin HTTP, que se prueban con una sesión de base de datos
(principio 10). Todas las consultas filtran por `space_id` (RF-29).
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import dates
from app.models import BudgetItem, Category, Income, category_key
from app.schemas import SkippedItemOut

PlanRow = type[BudgetItem] | type[Income]


def stored_name(
    db: Session,
    model: PlanRow,
    space_id: int,
    period_start: date,
    name: str,
    exclude_id: int | None = None,
) -> str | None:
    """Nombre guardado del rubro o ingreso del mes equivalente a `name`, o
    `None` si no hay ninguno (RF-3, decisión 22).

    `exclude_id` deja fuera la fila que se está editando: cambiar solo las
    mayúsculas de su propio nombre no choca consigo misma.
    """
    query = select(model.name).where(
        model.space_id == space_id,
        model.period_start == period_start,
        model.name_key == category_key(name),
    )
    if exclude_id is not None:
        query = query.where(model.id != exclude_id)
    return db.scalar(query)


class PlanNotEmpty(Exception):
    """El mes destino ya tiene rubros o ingresos (RF-14)."""


class NothingToCopy(Exception):
    """El mes anterior no tiene nada que copiar (RF-15)."""


def has_plan(db: Session, space_id: int, period_start: date) -> bool:
    """Si el mes tiene algún rubro o algún ingreso."""
    for model in (BudgetItem, Income):
        found = db.scalar(
            select(model.id)
            .where(model.space_id == space_id, model.period_start == period_start)
            .limit(1)
        )
        if found is not None:
            return True
    return False


def copy_previous_plan(db: Session, space_id: int, period: str) -> list[SkippedItemOut]:
    """Copia al mes `period` los rubros y los ingresos del mes inmediatamente
    anterior, y devuelve los rubros que omitió (RF-13, decisiones 2, 9 y 15).

    - Los rubros de categorías eliminadas no se copian.
    - Lanza `PlanNotEmpty` si el destino ya tiene plan (RF-14), y
      `NothingToCopy` si el origen no tiene nada que copiar (RF-15).
    - Todo o nada: un solo `commit`. Si otra copia llegó a la vez, el índice
      único frena el `INSERT`, se deshace todo y se responde como destino con
      plan (RF-14).
    - No cambia el origen ni ningún gasto (RF-16).
    """
    target, _ = dates.period_bounds(period)
    source, _ = dates.period_bounds(dates.previous_period(period))
    if has_plan(db, space_id, target):
        raise PlanNotEmpty

    items = db.execute(
        select(BudgetItem, Category)
        .join(Category, Category.id == BudgetItem.category_id)
        .where(BudgetItem.space_id == space_id, BudgetItem.period_start == source)
        .order_by(BudgetItem.id)
    ).all()
    incomes = db.scalars(
        select(Income)
        .where(Income.space_id == space_id, Income.period_start == source)
        .order_by(Income.id)
    ).all()
    kept = [item for item, category in items if category.deleted_at is None]
    skipped = [
        SkippedItemOut(name=item.name, category=category.name)
        for item, category in items
        if category.deleted_at is not None
    ]
    if not kept and not incomes:
        raise NothingToCopy

    db.add_all(
        BudgetItem(
            space_id=space_id,
            period_start=target,
            name=item.name,
            category_id=item.category_id,
            amount=item.amount,
        )
        for item in kept
    )
    db.add_all(
        Income(
            space_id=space_id,
            period_start=target,
            name=income.name,
            amount=income.amount,
        )
        for income in incomes
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise PlanNotEmpty from None
    return skipped
