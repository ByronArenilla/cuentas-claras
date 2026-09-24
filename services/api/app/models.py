"""Tablas de usuarios, espacios, membresías, invitaciones y sesiones."""

from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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
    __tablename__ = "invitations"
    # Solo la invitación de espacio apunta a un espacio (RF-15, RF-16).
    __table_args__ = (
        CheckConstraint(
            "(kind = 'instance' AND space_id IS NULL)"
            " OR (kind = 'space' AND space_id IS NOT NULL)",
            name="invitation_kind_matches_space",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Se guarda el hash y no el código: una copia de la base de datos no
    # entrega invitaciones utilizables.
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(10))
    space_id: Mapped[int | None] = mapped_column(
        ForeignKey("spaces.id", ondelete="CASCADE")
    )
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
