"""Invitaciones: códigos de un solo uso con caducidad de 24 horas (RF-15 a RF-19)."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models import Invitation, User
from app.schemas import InvitationOut
from app.security import generate_invitation_code, hash_token

INVITATION_LIFETIME = timedelta(hours=24)

router = APIRouter(prefix="/invitations", tags=["invitations"])


def find_valid_invitation(db: Session, code: str) -> Invitation | None:
    """Invitación sin usar y sin caducar que corresponde al código, o None."""
    invitation = db.scalar(
        select(Invitation).where(Invitation.code_hash == hash_token(code))
    )
    if invitation is None or invitation.used_at is not None:
        return None
    if invitation.expires_at <= datetime.now(UTC):
        return None
    return invitation


def claim_invitation(db: Session, invitation: Invitation, user_id: int) -> bool:
    """Marca la invitación como usada; False si otra petición la usó antes.

    El `WHERE used_at IS NULL` hace que la comprobación y la marca sean una
    sola sentencia: si dos registros llegan a la vez con el mismo código,
    solo uno actualiza la fila y el otro recibe False (RF-19).
    """
    result = db.execute(
        update(Invitation)
        .where(Invitation.id == invitation.id, Invitation.used_at.is_(None))
        .values(used_at=datetime.now(UTC), used_by=user_id)
    )
    return result.rowcount == 1


@router.post("/instance", status_code=status.HTTP_201_CREATED)
def create_instance_invitation(
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> InvitationOut:
    """Código para crear una cuenta sin unirse a ningún espacio (RF-16)."""
    code = generate_invitation_code()
    invitation = Invitation(
        code_hash=hash_token(code),
        kind="instance",
        created_by=user.id,
        expires_at=datetime.now(UTC) + INVITATION_LIFETIME,
    )
    db.add(invitation)
    db.commit()
    return InvitationOut(code=code, expires_at=invitation.expires_at)
