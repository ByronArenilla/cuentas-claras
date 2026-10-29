"""Categorías de un espacio: las predefinidas, listar y crear (spec 002).

Las rutas reciben el espacio por `member_space`, nunca consultando por
`space_id` directamente (RF-10, RF-29 de la 001).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import member_space
from app.models import Category, Space, category_key
from app.schemas import CategoryIn, CategoryOut

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


def existing_name(db: Session, space_id: int, name: str) -> str | None:
    """Nombre guardado de la categoría del espacio equivalente a `name`
    según la decisión 4, o `None` si no hay ninguna."""
    return db.scalar(
        select(Category.name).where(
            Category.space_id == space_id,
            Category.name_key == category_key(name),
        )
    )


def duplicate(name: str) -> HTTPException:
    # Muestra el nombre guardado: así se entiende por qué "comida" choca con
    # "Comida" (plan 002).
    return HTTPException(
        status.HTTP_409_CONFLICT, f"Ya existe la categoría «{name}» en este espacio."
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_category(
    data: CategoryIn,
    space: Annotated[Space, Depends(member_space)],
    db: Annotated[Session, Depends(get_db)],
) -> CategoryOut:
    """Crea una categoría en el espacio; cualquier miembro puede (RF-5,
    decisión 6). Un nombre equivalente a otro del espacio se rechaza (RF-8)."""
    if (stored := existing_name(db, space.id, data.name)) is not None:
        raise duplicate(stored)

    category = Category(space_id=space.id, name=data.name)
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        # Otra petición creó el mismo nombre entre la comprobación y el
        # guardado: el índice único la frena y el rollback no deja nada.
        db.rollback()
        raise duplicate(existing_name(db, space.id, data.name) or data.name) from None
    return CategoryOut.model_validate(category)
