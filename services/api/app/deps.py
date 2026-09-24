"""Dependencias de FastAPI que identifican a quien llama (RF-10, RF-11).

Toda ruta protegida depende de `current_user` (o de `current_session`): si la
petición no trae una sesión válida, FastAPI responde `401` antes de ejecutar
la ruta, así que la operación nunca llega a empezar.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Session as SessionRow
from app.models import User
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
