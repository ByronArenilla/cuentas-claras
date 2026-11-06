"""Tarjetas de un espacio: crear, listar, editar y eliminar (spec 009, RF-1 a
RF-8).

Eliminar una tarjeta la archiva, como una categoría: `deleted_at` deja de
ser nula y sus compras, abonos y extractos la conservan (decisión 9).

Las rutas reciben el espacio por `member_space`, nunca consultando por
`space_id` directamente (RF-42; RF-28 y RF-29 de la 001).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import member_space
from app.models import Card, Space, category_key, utc_now
from app.schemas import CardDeletedOut, CardIn, CardOut, CardPatch, rate_to_bp

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
