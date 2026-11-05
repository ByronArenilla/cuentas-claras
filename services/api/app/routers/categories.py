"""Categorías de un espacio: las predefinidas, listar y crear (spec 002), y
eliminar y restaurar (spec 008).

Eliminar una categoría la archiva: `deleted_at` deja de ser nula, y la fila
sigue ahí para los rubros y gastos que ya la tenían (decisión 14 de la 008).

Las rutas reciben el espacio por `member_space`, nunca consultando por
`space_id` directamente (RF-10, RF-29 de la 001).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import member_space
from app.models import Category, Space, category_key, utc_now
from app.schemas import CategoryDeletedOut, CategoryIn, CategoryOut

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
    """Categorías activas del espacio en orden de creación: primero las
    predefinidas y después las nuevas (RF-4, decisión 5). Las eliminadas no
    salen: ya no son una opción (RF-39 de la 008)."""
    categories = db.scalars(
        select(Category)
        .where(Category.space_id == space.id, Category.deleted_at.is_(None))
        .order_by(Category.id)
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


def deleted_category(db: Session, space_id: int, name: str) -> Category | None:
    """Categoría eliminada del espacio con un nombre equivalente a `name`."""
    return db.scalar(
        select(Category).where(
            Category.space_id == space_id,
            Category.name_key == category_key(name),
            Category.deleted_at.is_not(None),
        )
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_category(
    data: CategoryIn,
    space: Annotated[Space, Depends(member_space)],
    db: Annotated[Session, Depends(get_db)],
    response: Response,
) -> CategoryOut:
    """Crea una categoría en el espacio; cualquier miembro puede (RF-5,
    decisión 6). Un nombre equivalente a otro del espacio se rechaza (RF-8).

    Si el nombre es el de una categoría eliminada, la restaura con su `id` y
    su nombre original y responde `200`: no se creó nada nuevo (RF-43 de la
    008, decisiones 16 y 21).
    """
    if (deleted := deleted_category(db, space.id, data.name)) is not None:
        deleted.deleted_at = None
        db.commit()
        response.status_code = status.HTTP_200_OK
        return CategoryOut.model_validate(deleted)

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


CATEGORY_NOT_FOUND = HTTPException(
    status.HTTP_404_NOT_FOUND, "Categoría no encontrada."
)


def active_space_category(
    category_id: int,
    space: Annotated[Space, Depends(member_space)],
    db: Annotated[Session, Depends(get_db)],
) -> Category:
    """Categoría activa de la ruta, solo si es del espacio que ya validó
    `member_space`. Una de otro espacio, inexistente o ya eliminada responde
    igual: `404` (RF-44 de la 008)."""
    category = db.scalar(
        select(Category).where(
            Category.id == category_id,
            Category.space_id == space.id,
            Category.deleted_at.is_(None),
        )
    )
    if category is None:
        raise CATEGORY_NOT_FOUND
    return category


def deleted_message(name: str) -> str:
    return (
        f"Eliminaste «{name}». Sus rubros y gastos la conservan, pero sus rubros "
        "ya no se copiarán al planear. Para volver a usarla, créala de nuevo con "
        "el mismo nombre."
    )


@router.delete("/{category_id}")
def delete_category(
    category: Annotated[Category, Depends(active_space_category)],
    db: Annotated[Session, Depends(get_db)],
) -> CategoryDeletedOut:
    """Elimina (archiva) la categoría, sin pedir confirmación: no borra ningún
    rubro ni gasto, que la conservan (RF-39, RF-40 de la 008). Responde con
    el aviso de cómo volver a usarla (decisión 23)."""
    category.deleted_at = utc_now()
    db.commit()
    return CategoryDeletedOut(
        id=category.id, name=category.name, message=deleted_message(category.name)
    )


def usable_category(db: Session, space_id: int, category_id: int) -> Category:
    """Categoría que se puede elegir para un rubro o un gasto: del espacio y
    activa. Lanza `422` si no.

    Una de otro espacio responde igual que una inexistente (RF-5 de la 003).
    Una eliminada es del propio espacio, así que el mensaje puede decir cómo
    restaurarla (RF-41 de la 008).
    """
    category = db.scalar(
        select(Category).where(
            Category.id == category_id, Category.space_id == space_id
        )
    )
    if category is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "La categoría no existe en este espacio.",
        )
    if category.deleted_at is not None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"La categoría «{category.name}» fue eliminada. Para usarla de nuevo, "
            "créala otra vez con el mismo nombre.",
        )
    return category
