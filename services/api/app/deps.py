"""Dependencias de FastAPI: quién llama y a qué espacio puede acceder.

Toda ruta protegida depende de `current_user` (o de `current_session`): si la
petición no trae una sesión válida, FastAPI responde `401` antes de ejecutar
la ruta, así que la operación nunca llega a empezar (RF-10, RF-11).

Toda ruta que recibe un `space_id` depende de `member_space`: es la pieza que
sostiene el aislamiento entre espacios (principio 5, RF-29, RF-30, RF-32).
"""

import hmac
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, dates
from app.db import get_db
from app.models import Membership, Space, User
from app.models import Session as SessionRow
from app.schemas import PERIOD_FORMAT_MESSAGE
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


INVALID_PERIOD = HTTPException(
    status.HTTP_422_UNPROCESSABLE_CONTENT, PERIOD_FORMAT_MESSAGE
)


def requested_period(period: str | None = None) -> str:
    """Periodo `?period=YYYY-MM` de la consulta, por defecto el actual en `TZ`.

    La comparten el listado de gastos (RF-10 y RF-11 de la 003) y el resumen
    (RF-15 de la 004), así que un periodo mal escrito recibe en las dos el
    mismo `422`.
    """
    if period is None:
        return dates.period_of(dates.today())
    try:
        dates.period_bounds(period)
    except ValueError:
        raise INVALID_PERIOD from None
    return period


# auto_error=False por la misma razón que `bearer`: el 401 y su mensaje los
# decide esta capa. También declara la llave en /docs (botón "Authorize").
bot_key_header = APIKeyHeader(name="X-Bot-Key", auto_error=False)

INVALID_BOT_KEY = HTTPException(
    status.HTTP_401_UNAUTHORIZED, "Llave del bot no válida."
)


def bot_client(key: Annotated[str | None, Depends(bot_key_header)]) -> None:
    """Exige la llave del bot en `X-Bot-Key` (RF-9 de la 005).

    `compare_digest` tarda lo mismo acierte o no la llave, así que medir el
    tiempo de respuesta no ayuda a adivinarla. Se lee `config.settings` en
    cada llamada para que los tests puedan sustituir la configuración.
    """
    expected = config.settings.bot_api_key.encode()
    if key is None or not hmac.compare_digest(key.encode(), expected):
        raise INVALID_BOT_KEY
