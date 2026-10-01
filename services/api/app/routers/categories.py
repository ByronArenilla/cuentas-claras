"""Categorías de un espacio: las predefinidas, listar y crear (spec 002).

Las rutas reciben el espacio por `member_space`, nunca consultando por
`space_id` directamente (RF-10, RF-29 de la 001).
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import member_space
from app.models import Category, Space
from app.schemas import CategoryOut

# Se copian en cada espacio nuevo, en este orden (spec 002, decisiones 1 y 2).
# Cambiarlas solo afecta a los espacios que se creen después.
DEFAULT_CATEGORIES = (
    "Hogar",
    "Comida",
    "Transporte",
    "Salud",
    "Servicios",
    "Ocio",
    "Otros",
)

router = APIRouter(prefix="/spaces/{space_id}/categories", tags=["categories"])


def add_default_categories(db: Session, space_id: int) -> None:
    """Añade las predefinidas al espacio sin hacer `commit`: lo hace quien creó
    el espacio, para que todo entre en la misma transacción (RF-1)."""
    db.add_all(Category(space_id=space_id, name=name) for name in DEFAULT_CATEGORIES)


@router.get("")
def list_categories(
    space: Annotated[Space, Depends(member_space)],
    db: Annotated[Session, Depends(get_db)],
) -> list[CategoryOut]:
    """Categorías del espacio en orden de creación: primero las predefinidas
    y después las nuevas (RF-4, decisión 5)."""
    categories = db.scalars(
        select(Category).where(Category.space_id == space.id).order_by(Category.id)
    )
    return [CategoryOut.model_validate(category) for category in categories]
