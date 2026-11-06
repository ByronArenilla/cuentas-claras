"""Tarjetas de un espacio: crear, listar, editar y eliminar (spec 009, RF-1 a
RF-8), el valor real de su extracto en un mes (RF-31 a RF-33) y pagar
todo (RF-29, RF-30).

Eliminar una tarjeta la archiva, como una categoría: `deleted_at` deja de
ser nula y sus compras, abonos y extractos la conservan (decisión 9).

Las rutas reciben el espacio por `member_space`, nunca consultando por
`space_id` directamente (RF-42; RF-28 y RF-29 de la 001).
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import dates
from app.db import get_db
from app.debts import LaterPrepayment, NothingToPayOff, card_month, pay_off
from app.deps import INVALID_PERIOD, current_user, member_space
from app.models import Card, CardStatement, Space, User, category_key, utc_now
from app.schemas import (
    CardDeletedOut,
    CardIn,
    CardOut,
    CardPatch,
    PayoffIn,
    PayoffOut,
    PrepaymentOut,
    StatementIn,
    StatementOut,
    rate_to_bp,
)

router = APIRouter(prefix="/spaces/{space_id}/cards", tags=["cards"])

CARD_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Tarjeta no encontrada.")


def same_name(db: Session, space_id: int, name: str) -> Card | None:
    """Tarjeta del espacio, activa o archivada, con un nombre equivalente a
    `name` según la comparación de la 002 (RF-2)."""
    return db.scalar(
        select(Card).where(
            Card.space_id == space_id, Card.name_key == category_key(name)
        )
    )


def duplicate(name: str) -> HTTPException:
    # Nombra la que ya existe, con su escritura, como las categorías.
    return HTTPException(status.HTTP_409_CONFLICT, f"Ya existe la tarjeta «{name}».")


def commit_or_duplicate(db: Session, space_id: int, name: str) -> None:
    """Guarda; si otra petición guardó el mismo nombre entre la comprobación
    y el guardado, el índice único la frena y el rollback no deja nada."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        stored = same_name(db, space_id, name)
        raise duplicate(stored.name if stored else name) from None


@router.post("", status_code=status.HTTP_201_CREATED)
def create_card(
    data: CardIn,
    space: Annotated[Space, Depends(member_space)],
    db: Annotated[Session, Depends(get_db)],
    response: Response,
) -> CardOut:
    """Crea una tarjeta en el espacio (RF-1). Un nombre equivalente al de una
    activa se rechaza (RF-2).

    Si el nombre es el de una archivada, la restaura con su `id`, su nombre,
    sus días y su tasa originales, y responde `200`: no se creó nada nuevo
    (RF-7, decisión 24).
    """
    if (existing := same_name(db, space.id, data.name)) is not None:
        if existing.deleted_at is None:
            raise duplicate(existing.name)
        existing.deleted_at = None
        db.commit()
        response.status_code = status.HTTP_200_OK
        return CardOut.of(existing)

    card = Card(
        space_id=space.id,
        name=data.name,
        cutoff_day=data.cutoff_day,
        due_day=data.due_day,
        monthly_rate_bp=rate_to_bp(data.monthly_rate),
    )
    db.add(card)
    commit_or_duplicate(db, space.id, data.name)
    return CardOut.of(card)


@router.get("")
def list_cards(
    space: Annotated[Space, Depends(member_space)],
    db: Annotated[Session, Depends(get_db)],
) -> list[CardOut]:
    """Tarjetas activas del espacio en orden de creación (RF-4). Las
    archivadas no salen: ya no son una opción para compras nuevas (RF-6)."""
    cards = db.scalars(
        select(Card)
        .where(Card.space_id == space.id, Card.deleted_at.is_(None))
        .order_by(Card.id)
    )
    return [CardOut.of(card) for card in cards]


def space_card(
    card_id: int,
    space: Annotated[Space, Depends(member_space)],
    db: Annotated[Session, Depends(get_db)],
) -> Card:
    """Tarjeta de la ruta, activa o archivada, solo si es del espacio que ya
    validó `member_space`. Una de otro espacio responde igual que una
    inexistente (RF-8)."""
    card = db.scalar(select(Card).where(Card.id == card_id, Card.space_id == space.id))
    if card is None:
        raise CARD_NOT_FOUND
    return card


@router.patch("/{card_id}")
def update_card(
    data: CardPatch,
    card: Annotated[Card, Depends(space_card)],
    db: Annotated[Session, Depends(get_db)],
) -> CardOut:
    """Cambia solo lo enviado, también en una tarjeta archivada (RF-5,
    decisión 25). Cambiar los días no mueve las compras ya registradas: su
    mes de pago está guardado (decisión 13)."""
    changes = data.model_dump(exclude_unset=True)

    if "name" in changes:
        other = same_name(db, card.space_id, changes["name"])
        if other is not None and other.id != card.id:
            raise duplicate(other.name)
        card.name = changes["name"]
    for field in ("cutoff_day", "due_day"):
        if field in changes:
            setattr(card, field, changes[field])
    if "monthly_rate" in changes:
        card.monthly_rate_bp = rate_to_bp(changes["monthly_rate"])

    commit_or_duplicate(db, card.space_id, card.name)
    return CardOut.of(card)


def deleted_message(name: str) -> str:
    return (
        f"Eliminaste «{name}». Sus cuotas pendientes siguen llegando a Deudas. "
        "Para volver a usarla en compras nuevas, créala de nuevo con el mismo "
        "nombre."
    )


@router.delete("/{card_id}")
def delete_card(
    card: Annotated[Card, Depends(space_card)],
    db: Annotated[Session, Depends(get_db)],
) -> CardDeletedOut:
    """Elimina (archiva) la tarjeta, sin pedir confirmación: no borra compras,
    abonos ni extractos (RF-6). Una ya archivada responde `404` (RF-8)."""
    if card.deleted_at is not None:
        raise CARD_NOT_FOUND
    card.deleted_at = utc_now()
    db.commit()
    return CardDeletedOut(
        id=card.id, name=card.name, message=deleted_message(card.name)
    )


def usable_card(db: Session, space_id: int, card_id: int) -> Card:
    """Tarjeta que se puede elegir para una compra: del espacio y activa.
    Lanza `422` si no.

    Una de otro espacio responde igual que una inexistente (RF-12). Una
    archivada es del propio espacio, así que el mensaje puede decir cómo
    restaurarla, como las categorías (RF-41 de la 008).
    """
    card = db.scalar(select(Card).where(Card.id == card_id, Card.space_id == space_id))
    if card is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "La tarjeta no existe en este espacio.",
        )
    if card.deleted_at is not None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"La tarjeta «{card.name}» fue eliminada. Para usarla de nuevo, "
            "créala otra vez con el mismo nombre.",
        )
    return card


def first_due_start(card: Card, spent_on: date) -> date:
    """Día 1 del mes de pago de la primera cuota de una compra del día
    `spent_on` con `card`, con los días actuales de la tarjeta (RF-13,
    decisión 12). Se guarda en la compra (decisión 13)."""
    period = dates.first_due_period(spent_on, card.cutoff_day, card.due_day)
    return dates.period_bounds(period)[0]


# --- Valor real del extracto (RF-31 a RF-33) ---


def path_period(period: str) -> date:
    """Día 1 del periodo de la ruta. Un periodo mal escrito responde `422`
    con el mismo mensaje que el resto de la API (plan 004)."""
    try:
        return dates.period_bounds(period)[0]
    except ValueError:
        raise INVALID_PERIOD from None


def card_statement(db: Session, card: Card, start: date) -> CardStatement | None:
    return db.scalar(
        select(CardStatement).where(
            CardStatement.card_id == card.id,
            CardStatement.space_id == card.space_id,
            CardStatement.period_start == start,
        )
    )


@router.put("/{card_id}/statements/{period}")
def write_statement(
    period: str,
    data: StatementIn,
    card: Annotated[Card, Depends(space_card)],
    db: Annotated[Session, Depends(get_db)],
) -> StatementOut:
    """Escribe o reemplaza el valor real del extracto de la tarjeta, activa o
    archivada, en el mes (RF-31, decisión 25). Reemplaza la deuda estimada
    de ese mes en Deudas (RF-35)."""
    start = path_period(period)
    statement = card_statement(db, card, start)
    if statement is None:
        statement = CardStatement(
            space_id=card.space_id, card_id=card.id, period_start=start
        )
        db.add(statement)
    statement.amount = data.amount
    try:
        db.commit()
    except IntegrityError:
        # Otro `PUT` del mismo mes lo creó entre la lectura y el guardado: se
        # actualiza ese. Gana el último, como se espera de un `PUT`.
        db.rollback()
        statement = card_statement(db, card, start)
        assert statement is not None
        statement.amount = data.amount
        db.commit()
    return StatementOut.model_validate(statement)


@router.delete("/{card_id}/statements/{period}", status_code=status.HTTP_204_NO_CONTENT)
def delete_statement(
    period: str,
    card: Annotated[Card, Depends(space_card)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Quita el valor real del mes, sin pedir confirmación: la deuda vuelve a
    ser la estimada (RF-32, decisión 20)."""
    statement = card_statement(db, card, path_period(period))
    if statement is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"{period} no tiene valor del extracto para esta tarjeta.",
        )
    db.delete(statement)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Pagar todo (RF-29, RF-30) ---


@router.post("/{card_id}/payoff", status_code=status.HTTP_201_CREATED)
def pay_off_card(
    data: PayoffIn,
    card: Annotated[Card, Depends(space_card)],
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PayoffOut:
    """Paga el total de la tarjeta, activa o archivada, en el mes: salda con
    un abono cada compra que ya está en el extracto (RF-29, decisión 28). Las
    compras posteriores al corte siguen llegando en su mes (RF-30)."""
    try:
        created = pay_off(db, card, data.period, user.id)
    except NothingToPayOff:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"La tarjeta «{card.name}» no tiene compras con saldo después de la "
            f"cuota de {data.period}; no se creó ningún abono.",
        ) from None
    except LaterPrepayment as conflict:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"«{conflict.purchase.description}» ya tiene un abono en "
            f"{conflict.period}. Bórralo para pagar todo en {data.period}; no se "
            "creó ningún abono.",
        ) from None
    db.commit()
    return PayoffOut(
        period=data.period,
        prepayments=[PrepaymentOut.model_validate(row) for row in created],
        debt=card_month(db, card, data.period).amount,
    )
