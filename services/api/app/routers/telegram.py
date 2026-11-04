"""Vinculación de chats de Telegram y sesiones del bot (spec 005).

El usuario pide un código con su sesión; el bot lo canjea con su llave y,
desde entonces, pide sesiones de una hora para actuar en nombre del usuario
del chat (decisiones 1 y 7).
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models import TelegramLinkCode, User
from app.schemas import LinkCodeOut
from app.security import generate_link_code, hash_token, normalize_link_code

LINK_CODE_LIFETIME = timedelta(minutes=10)

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/link-codes", status_code=status.HTTP_201_CREATED)
def create_link_code(
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> LinkCodeOut:
    """Código de un solo uso que caduca a los 10 minutos (RF-1). Se guarda
    solo su hash, y el código no se vuelve a mostrar (RF-2)."""
    code = generate_link_code()
    link_code = TelegramLinkCode(
        code_hash=hash_token(normalize_link_code(code)),
        user_id=user.id,
        expires_at=datetime.now(UTC) + LINK_CODE_LIFETIME,
    )
    db.add(link_code)
    db.commit()
    return LinkCodeOut(code=code, expires_at=link_code.expires_at)
