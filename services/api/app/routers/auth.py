"""Registro y sesión: entrar, identificarse y salir (RF-1 a RF-12)."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_session, current_user
from app.models import Membership, Space, User
from app.models import Session as SessionRow
from app.schemas import LoginIn, RegisterIn, RegisterOut, SpaceOut, TokenOut, UserOut
from app.security import (
    generate_session_token,
    hash_password,
    hash_token,
    verify_password,
)

# Nombre fijo del espacio que se crea con cada usuario (spec 001, decisión 7).
PERSONAL_SPACE_NAME = "Personal"

SESSION_LIFETIME = timedelta(days=15)

EMAIL_TAKEN = "Ya existe una cuenta con ese correo."

# Mismo mensaje falle el correo o la contraseña (RF-9).
BAD_CREDENTIALS = "Correo o contraseña incorrectos."

# Hash de una contraseña que nadie usa. Cuando el correo no existe se verifica
# igualmente contra él, para que la respuesta tarde lo mismo que con una
# contraseña equivocada y el tiempo no delate qué correos están registrados.
_DUMMY_HASH = hash_password("contraseña-que-nadie-usa")

router = APIRouter(tags=["auth"])


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
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


@router.post("/auth/login")
def login(data: LoginIn, db: Annotated[Session, Depends(get_db)]) -> TokenOut:
    """Crea una sesión de 15 días y entrega su token; guarda solo el hash (RF-8)."""
    email = data.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    password_hash = user.password_hash if user else _DUMMY_HASH
    if not verify_password(password_hash, data.password) or user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_CREDENTIALS)

    token = generate_session_token()
    session = SessionRow(
        token_hash=hash_token(token),
        user_id=user.id,
        expires_at=datetime.now(UTC) + SESSION_LIFETIME,
    )
    db.add(session)
    db.commit()
    return TokenOut(access_token=token, expires_at=session.expires_at)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    session: Annotated[SessionRow, Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Borra la sesión actual: el token deja de servir desde ya (RF-12)."""
    db.delete(session)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me")
def me(user: Annotated[User, Depends(current_user)]) -> UserOut:
    """Quién soy, según el token de la petición (RF-10)."""
    return UserOut.model_validate(user)
