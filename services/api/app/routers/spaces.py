"""Espacios: crear, listar, invitar, salir y borrar (RF-13 a RF-27, RF-35).

Las rutas que reciben un `space_id` resuelven el espacio con la dependencia
`member_space`, nunca consultando por `space_id` directamente (RF-29).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import ScalarSelect

from app.db import get_db
from app.deps import current_user, member_space
from app.models import Membership, Space, User
from app.routers.invitations import issue_invitation
from app.schemas import InvitationOut, SpaceIn, SpaceOut

ONLY_SPACE = "No puedes salir de tu único espacio: necesitas al menos uno."
ONLY_SPACE_DELETE = "No puedes borrar tu único espacio: necesitas al menos uno."
SHARED_SPACE = (
    "Este espacio tiene más miembros. Solo se puede borrar cuando eres "
    "su único miembro."
)
WRONG_CONFIRMATION = "El nombre de confirmación no coincide con el del espacio."
LAST_MEMBER = (
    "Eres el último miembro de este espacio y no puedes salir. "
    "Si quieres deshacerte de él, bórralo."
)

router = APIRouter(prefix="/spaces", tags=["spaces"])


def count_members(space_id: int) -> ScalarSelect[int]:
    return select(func.count()).where(Membership.space_id == space_id).scalar_subquery()


def count_spaces(user_id: int) -> ScalarSelect[int]:
    return select(func.count()).where(Membership.user_id == user_id).scalar_subquery()


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


@router.post("/{space_id}/invitations", status_code=status.HTTP_201_CREATED)
def create_space_invitation(
    space: Annotated[Space, Depends(member_space)],
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> InvitationOut:
    """Código para unirse a este espacio; solo lo emite un miembro (RF-15)."""
    return issue_invitation(db, user.id, "space", space.id)


@router.delete("/{space_id}/members/me", status_code=status.HTTP_204_NO_CONTENT)
def leave_space(
    space: Annotated[Space, Depends(member_space)],
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Borra la membresía de quien llama; el espacio y sus datos se quedan.

    Primero se comprueba el único espacio: si además es su último miembro,
    "bórralo" no sería una salida, porque RF-26 impide borrar el único espacio.
    """
    if db.scalar(select(count_spaces(user.id))) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, ONLY_SPACE)
    if db.scalar(select(count_members(space.id))) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, LAST_MEMBER)

    # Las dos condiciones se repiten dentro del DELETE: si dos miembros salen
    # a la vez, la sentencia ya no borra nada cuando solo queda uno, y el
    # espacio nunca se queda sin miembros.
    result = db.execute(
        delete(Membership).where(
            Membership.user_id == user.id,
            Membership.space_id == space.id,
            count_members(space.id) > 1,
            count_spaces(user.id) > 1,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, LAST_MEMBER)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{space_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_space(
    space: Annotated[Space, Depends(member_space)],
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    confirm: str,
) -> Response:
    """Borra el espacio y, en cascada, sus membresías, invitaciones y datos.

    El nombre de confirmación viaja como parámetro de consulta porque un
    `DELETE` con cuerpo es ambiguo (plan 001). Se compara tal cual: sin
    quitar espacios ni ignorar mayúsculas (RF-25).
    """
    if db.scalar(select(count_members(space.id))) > 1:
        raise HTTPException(status.HTTP_409_CONFLICT, SHARED_SPACE)
    if db.scalar(select(count_spaces(user.id))) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, ONLY_SPACE_DELETE)
    if confirm != space.name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, WRONG_CONFIRMATION)

    # Las condiciones se repiten dentro del DELETE: si alguien canjea una
    # invitación justo ahora, la sentencia no borra nada y nadie pierde un
    # espacio que no aceptó perder (RF-24). El resto lo borra la base de datos
    # con ON DELETE CASCADE (RF-23).
    result = db.execute(
        delete(Space).where(
            Space.id == space.id,
            count_members(space.id) == 1,
            count_spaces(user.id) > 1,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, SHARED_SPACE)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
