"""Dependencias de FastAPI: quién llama y a qué espacio puede acceder.

Toda ruta protegida depende de `current_user` (o de `current_session`): si la
petición no trae una sesión válida, FastAPI responde `401` antes de ejecutar
la ruta, así que la operación nunca llega a empezar (RF-10, RF-11).

Toda ruta que recibe un `space_id` depende de `member_space`: es la pieza que
sostiene el aislamiento entre espacios (principio 5, RF-29, RF-30, RF-32).
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Membership, Space, User
from app.models import Session as SessionRow
from app.security import hash_token

# auto_error=False: sin cabecera devuelve None y el 401 lo decide esta capa,
# con el mismo mensaje para todos los casos. Además, declara el esquema en
# /docs, que muestra el botón "Authorize" para probar las rutas protegidas.
bearer = HTTPBearer(auto_error=False)

UNAUTHORIZED = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    "Sesión no válida o caducada. Inicia sesión de nuevo.",
    headers={"WWW-Authenticate": "Bearer"},
)


def current_session(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> SessionRow:
    """Sesión vigente que respalda el token de la cabecera `Authorization`."""
    if credentials is None:
        raise UNAUTHORIZED
    session = db.scalar(
        select(SessionRow).where(
            SessionRow.token_hash == hash_token(credentials.credentials)
        )
    )
    # Una sesión caducada se rechaza sin borrarla: una petición sin sesión
    # válida no modifica nada (RF-11).
    if session is None or session.expires_at <= datetime.now(UTC):
        raise UNAUTHORIZED
    return session


def current_user(
    session: Annotated[SessionRow, Depends(current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Usuario al que pertenece la sesión de la petición."""
    return db.get_one(User, session.user_id)


SPACE_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Espacio no encontrado.")


def member_space(
    space_id: int,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Space:
    """Espacio indicado en la ruta, solo si quien llama es miembro.

    Un espacio ajeno responde igual que uno inexistente, `404` y no `403`:
    así la respuesta no revela qué espacios existen (RF-30).
    """
    space = db.scalar(
        select(Space)
        .join(Membership, Membership.space_id == Space.id)
        .where(Space.id == space_id, Membership.user_id == user.id)
    )
    if space is None:
        raise SPACE_NOT_FOUND
    return space
