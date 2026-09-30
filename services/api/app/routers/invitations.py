"""Invitaciones a un espacio: de un solo uso y con caducidad de 24 horas.

Cubre RF-15, RF-17, RF-19, RF-20, RF-36 y RF-37.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import current_user
from app.models import Invitation, Membership, Space, User
from app.schemas import InvitationOut, InvitationPreviewOut, SpaceOut
from app.security import generate_invitation_token, hash_token

INVITATION_LIFETIME = timedelta(hours=24)

# Mismo mensaje si la invitación no existe, ya se usó o caducó (RF-19).
INVITATION_INVALID = "La invitación no es válida, ya se usó o caducó."
ALREADY_MEMBER = "Ya eres miembro de este espacio."

router = APIRouter(prefix="/invitations", tags=["invitations"])


def find_valid_invitation(db: Session, token: str) -> Invitation | None:
    """Invitación sin usar y sin caducar que corresponde al token, o None."""
    invitation = db.scalar(
        select(Invitation).where(Invitation.code_hash == hash_token(token))
    )
    if invitation is None or invitation.used_at is not None:
        return None
    if invitation.expires_at <= datetime.now(UTC):
        return None
    return invitation


def claim_invitation(db: Session, invitation: Invitation, user_id: int) -> bool:
    """Marca la invitación como usada; False si otra petición la usó antes.

    El `WHERE used_at IS NULL` hace que la comprobación y la marca sean una
    sola sentencia: si dos canjes llegan a la vez con el mismo token,
    solo uno actualiza la fila y el otro recibe False (RF-19).
    """
    result = db.execute(
        update(Invitation)
        .where(Invitation.id == invitation.id, Invitation.used_at.is_(None))
        .values(used_at=datetime.now(UTC), used_by=user_id)
    )
    return result.rowcount == 1


def issue_invitation(db: Session, created_by: int, space_id: int) -> InvitationOut:
    """Guarda una invitación nueva y devuelve su enlace, que no se vuelve a ver."""
    token = generate_invitation_token()
    invitation = Invitation(
        code_hash=hash_token(token),
        space_id=space_id,
        created_by=created_by,
        expires_at=datetime.now(UTC) + INVITATION_LIFETIME,
    )
    db.add(invitation)
    db.commit()
    return InvitationOut(
        url=f"{settings.web_base_url}/unirse/{token}",
        expires_at=invitation.expires_at,
    )


@router.get("/{token}")
def preview_invitation(
    token: str, db: Annotated[Session, Depends(get_db)]
) -> InvitationPreviewOut:
    """Nombre del espacio y caducidad de una invitación vigente (RF-36).

    Sin sesión y sin escribir en la base de datos: las vistas previas de
    Telegram o WhatsApp abren el enlace y no deben gastarlo ni unir a nadie
    (RF-37). Una invitación no válida es un recurso que no existe: `404`,
    con el mismo mensaje que el canje (RF-19).
    """
    invitation = find_valid_invitation(db, token)
    if invitation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, INVITATION_INVALID)
    space = db.get_one(Space, invitation.space_id)
    return InvitationPreviewOut(space_name=space.name, expires_at=invitation.expires_at)


@router.post("/{token}/redeem")
def redeem_invitation(
    token: str,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> SpaceOut:
    """Une a quien llama al espacio de la invitación y la marca usada (RF-17)."""
    invitation = find_valid_invitation(db, token)
    if invitation is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, INVITATION_INVALID)

    # RF-20: quien ya es miembro no duplica la membresía ni gasta la invitación.
    already_member = db.scalar(
        select(Membership.id).where(
            Membership.user_id == user.id,
            Membership.space_id == invitation.space_id,
        )
    )
    if already_member is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, ALREADY_MEMBER)

    try:
        db.add(Membership(user_id=user.id, space_id=invitation.space_id))
        if not claim_invitation(db, invitation, user.id):
            db.rollback()
            raise HTTPException(status.HTTP_403_FORBIDDEN, INVITATION_INVALID)
        db.commit()
    except IntegrityError:
        # Dos canjes simultáneos del mismo usuario: el índice único frena el
        # segundo y el rollback deja la invitación sin usar.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, ALREADY_MEMBER) from None

    return SpaceOut.model_validate(db.get_one(Space, invitation.space_id))
