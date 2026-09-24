"""Invitaciones: códigos de un solo uso con caducidad de 24 horas (RF-15 a RF-20)."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models import Invitation, Membership, Space, User
from app.schemas import InvitationOut, SpaceOut
from app.security import generate_invitation_code, hash_token

INVITATION_LIFETIME = timedelta(hours=24)

# Mismo mensaje si el código no existe, ya se usó o caducó (RF-19).
INVITATION_INVALID = "El código de invitación no es válido, ya se usó o caducó."
ALREADY_MEMBER = "Ya eres miembro de este espacio."

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


def issue_invitation(
    db: Session, created_by: int, kind: str, space_id: int | None = None
) -> InvitationOut:
    """Guarda una invitación nueva y devuelve su código, que no se vuelve a ver."""
    code = generate_invitation_code()
    invitation = Invitation(
        code_hash=hash_token(code),
        kind=kind,
        space_id=space_id,
        created_by=created_by,
        expires_at=datetime.now(UTC) + INVITATION_LIFETIME,
    )
    db.add(invitation)
    db.commit()
    return InvitationOut(code=code, expires_at=invitation.expires_at)


@router.post("/instance", status_code=status.HTTP_201_CREATED)
def create_instance_invitation(
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> InvitationOut:
    """Código para crear una cuenta sin unirse a ningún espacio (RF-16)."""
    return issue_invitation(db, user.id, "instance")


@router.post("/{code}/redeem")
def redeem_invitation(
    code: str,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> SpaceOut:
    """Une a quien llama al espacio de la invitación y la marca usada (RF-17)."""
    invitation = find_valid_invitation(db, code)
    # Una invitación de instancia solo sirve para crear cuenta: aquí cuenta
    # como no válida y no se consume.
    if invitation is None or invitation.kind != "space":
        raise HTTPException(status.HTTP_403_FORBIDDEN, INVITATION_INVALID)

    # RF-20: quien ya es miembro no duplica la membresía ni gasta el código.
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
        # segundo y el rollback deja el código sin usar.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, ALREADY_MEMBER) from None

    return SpaceOut.model_validate(db.get_one(Space, invitation.space_id))
