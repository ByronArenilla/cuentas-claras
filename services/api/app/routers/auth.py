"""Registro de usuarios (RF-1, RF-3, RF-4, RF-5, RF-7)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Membership, Space, User
from app.schemas import RegisterIn, RegisterOut, SpaceOut
from app.security import hash_password

# Nombre fijo del espacio que se crea con cada usuario (spec 001, decisión 7).
PERSONAL_SPACE_NAME = "Personal"

EMAIL_TAKEN = "Ya existe una cuenta con ese correo."

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(data: RegisterIn, db: Annotated[Session, Depends(get_db)]) -> RegisterOut:
    """Crea usuario, espacio personal y membresía en una sola transacción."""
    if db.scalar(select(User.id).where(User.email == data.email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN)

    user = User(email=data.email, password_hash=hash_password(data.password))
    space = Space(name=PERSONAL_SPACE_NAME)
    db.add_all([user, space])
    try:
        db.flush()
        db.add(Membership(user_id=user.id, space_id=space.id))
        db.commit()
    except IntegrityError:
        # Otra petición registró el mismo correo entre la comprobación y el
        # guardado: el índice único lo frena y el rollback no deja nada a medias.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN) from None

    return RegisterOut(
        id=user.id,
        email=user.email,
        personal_space=SpaceOut.model_validate(space),
    )
