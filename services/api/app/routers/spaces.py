"""Espacios: crear y listar los propios (RF-13, RF-14).

Las rutas que reciben un `space_id` resuelven el espacio con la dependencia
`member_space`, nunca consultando por `space_id` directamente (RF-29).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models import Membership, Space, User
from app.schemas import SpaceIn, SpaceOut

router = APIRouter(prefix="/spaces", tags=["spaces"])


@router.get("")
def list_spaces(
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[SpaceOut]:
    """Espacios de los que quien llama es miembro, del más antiguo al más nuevo."""
    spaces = db.scalars(
        select(Space)
        .join(Membership, Membership.space_id == Space.id)
        .where(Membership.user_id == user.id)
        .order_by(Space.id)
    )
    return [SpaceOut.model_validate(space) for space in spaces]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_space(
    data: SpaceIn,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> SpaceOut:
    """Crea el espacio y deja a quien lo crea como miembro, en una transacción."""
    space = Space(name=data.name)
    db.add(space)
    db.flush()
    db.add(Membership(user_id=user.id, space_id=space.id))
    db.commit()
    return SpaceOut.model_validate(space)
