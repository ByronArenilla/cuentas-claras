"""Plan del mes: rubros e ingresos (spec 008).

Funciones sin HTTP, que se prueban con una sesión de base de datos
(principio 10). Todas las consultas filtran por `space_id` (RF-29).
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BudgetItem, Income, category_key

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
