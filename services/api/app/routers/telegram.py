"""Vinculación de chats de Telegram y sesiones del bot (spec 005).

El usuario pide un código con su sesión; el bot lo canjea con su llave y,
desde entonces, pide sesiones de una hora para actuar en nombre del usuario
del chat (decisiones 1 y 7). Las rutas del bot dependen de `bot_client`.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import bot_client, current_user
from app.models import TelegramChat, TelegramLinkCode, User
from app.routers.auth import create_session
from app.schemas import ChatIn, ChatLinkIn, ChatLinkOut, LinkCodeOut, TokenOut
from app.security import generate_link_code, hash_token, normalize_link_code

LINK_CODE_LIFETIME = timedelta(minutes=10)
# Si el chat se desvincula, el bot pierde el acceso como mucho una hora
# después (decisión 7).
BOT_SESSION_LIFETIME = timedelta(hours=1)

# Mismo mensaje si el código no existe, ya se usó o caducó (RF-4).
CODE_INVALID = HTTPException(
    status.HTTP_400_BAD_REQUEST, "El código no es válido, ya se usó o caducó."
)
CHAT_NOT_LINKED = HTTPException(
    status.HTTP_404_NOT_FOUND, "Este chat no está vinculado."
)
CHAT_BUSY = HTTPException(
    status.HTTP_409_CONFLICT,
    "Este chat se está vinculando en otra petición. Intenta de nuevo.",
)

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


def find_valid_link_code(db: Session, typed: str) -> TelegramLinkCode | None:
    """Código sin usar y sin caducar que corresponde a lo escrito, o None."""
    link_code = db.scalar(
        select(TelegramLinkCode).where(
            TelegramLinkCode.code_hash == hash_token(normalize_link_code(typed))
        )
    )
    if link_code is None or link_code.used_at is not None:
        return None
    if link_code.expires_at <= datetime.now(UTC):
        return None
    return link_code


def claim_link_code(db: Session, link_code: TelegramLinkCode) -> bool:
    """Marca el código como usado; False si otra petición lo usó antes.

    Comprobar y marcar es una sola sentencia gracias al `WHERE used_at IS
    NULL`, como al canjear una invitación (RF-4).
    """
    result = db.execute(
        update(TelegramLinkCode)
        .where(TelegramLinkCode.id == link_code.id, TelegramLinkCode.used_at.is_(None))
        .values(used_at=datetime.now(UTC))
    )
    return result.rowcount == 1


@router.post("/chats", dependencies=[Depends(bot_client)])
def link_chat(data: ChatLinkIn, db: Annotated[Session, Depends(get_db)]) -> ChatLinkOut:
    """Vincula el chat al usuario del código y gasta el código (RF-3). Un
    chat ya vinculado pasa al usuario del código nuevo (RF-5)."""
    link_code = find_valid_link_code(db, data.code)
    if link_code is None or not claim_link_code(db, link_code):
        db.rollback()
        raise CODE_INVALID

    chat = db.scalar(select(TelegramChat).where(TelegramChat.chat_id == data.chat_id))
    if chat is None:
        db.add(TelegramChat(chat_id=data.chat_id, user_id=link_code.user_id))
    else:
        chat.user_id = link_code.user_id
    try:
        db.commit()
    except IntegrityError:
        # Dos vinculaciones del mismo chat a la vez: el índice único frena la
        # segunda, y el rollback deja su código sin usar.
        db.rollback()
        raise CHAT_BUSY from None
    return ChatLinkOut(email=db.get_one(User, link_code.user_id).email)


@router.delete(
    "/chats/{chat_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(bot_client)],
)
def unlink_chat(chat_id: int, db: Annotated[Session, Depends(get_db)]) -> Response:
    """Quita la vinculación del chat (RF-6). Responde igual si no existía:
    el resultado es el mismo, el chat queda sin vincular."""
    db.execute(delete(TelegramChat).where(TelegramChat.chat_id == chat_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/sessions",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(bot_client)],
)
def create_bot_session(
    data: ChatIn, db: Annotated[Session, Depends(get_db)]
) -> TokenOut:
    """Sesión de una hora del usuario del chat (RF-10, decisión 7). El bot la
    usa como cualquier otra sesión, con `Authorization: Bearer`."""
    user_id = db.scalar(
        select(TelegramChat.user_id).where(TelegramChat.chat_id == data.chat_id)
    )
    if user_id is None:
        raise CHAT_NOT_LINKED
    return create_session(db, user_id, BOT_SESSION_LIFETIME)
