"""Tablas de usuarios, espacios, membresías, invitaciones, sesiones y categorías."""

import unicodedata
from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, validates


class UTCDateTime(TypeDecorator[datetime]):
    """Fecha guardada en UTC y devuelta siempre con zona horaria UTC.

    SQLite no guarda la zona horaria: sin esto, una fecha leída volvería sin
    zona y no se podría comparar con `datetime.now(UTC)` (principio 7).
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Las fechas deben llevar zona horaria.")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


class Space(Base):
    __tablename__ = "spaces"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


class Membership(Base):
    __tablename__ = "memberships"
    # La base de datos impide la membresía duplicada aunque dos peticiones
    # lleguen a la vez (RF-20).
    __table_args__ = (UniqueConstraint("user_id", "space_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    space_id: Mapped[int] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


class Invitation(Base):
    """Invitación a un espacio, de un solo uso (RF-15). Desde el ADR 0005 no
    hay invitación de instancia, así que toda invitación tiene espacio."""

    __tablename__ = "invitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Se guarda el hash y no el token: una copia de la base de datos no
    # entrega invitaciones utilizables. La columna conserva el nombre
    # `code_hash` porque `create_all` no renombra columnas (ADR 0004).
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    space_id: Mapped[int] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    used_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


# Virgulilla suelta que, detrás de una `n`, forma la `ñ` en la forma NFD.
_TILDE = "\u0303"


def category_key(name: str) -> str:
    """Clave con la que se comparan los nombres de categoría (spec 002, decisión 4).

    Ignora mayúsculas, tildes, diéresis y espacios alrededor, pero no la ñ:
    "Educación" y "educacion" dan la misma clave; "Año" y "Ano", no.
    """
    # NFD separa cada letra de su acento: "é" pasa a ser "e" + marca suelta.
    decomposed = unicodedata.normalize("NFD", name.strip().casefold())
    kept: list[str] = []
    for char in decomposed:
        is_enye = char == _TILDE and kept[-1:] == ["n"]
        if unicodedata.combining(char) and not is_enye:
            continue
        kept.append(char)
    # NFC vuelve a unir la "n" con su virgulilla en una sola "ñ".
    return unicodedata.normalize("NFC", "".join(kept))


class Category(Base):
    __tablename__ = "categories"
    # La base de datos impide dos nombres equivalentes en el mismo espacio
    # aunque dos peticiones lleguen a la vez (RF-8); en espacios distintos
    # el mismo nombre está permitido (RF-9).
    __table_args__ = (UniqueConstraint("space_id", "name_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    space_id: Mapped[int] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(50))
    # Solo para comparar; nunca sale en una respuesta. Sin límite de longitud
    # porque `casefold` puede alargar el texto ("ß" pasa a ser "ss").
    name_key: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)

    @validates("name")
    def _fill_name_key(self, _key: str, name: str) -> str:
        """Recalcula `name_key` cada vez que se asigna el nombre: así las dos
        columnas no pueden quedar desalineadas (plan 002)."""
        self.name_key = category_key(name)
        return name
