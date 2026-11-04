"""Tablas de usuarios, espacios, membresías, invitaciones, sesiones, categorías,
gastos y presupuestos."""

import unicodedata
from datetime import UTC, date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
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


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        # Última defensa si algo salta la validación de la API (RF-3, RF-4).
        CheckConstraint("amount > 0", name="ck_expenses_amount_positive"),
        CheckConstraint(
            "payment_type IN ('credit', 'debit')", name="ck_expenses_payment_type"
        ),
        # El listado filtra por espacio y periodo (RF-9), igual que el
        # resumen de la spec 004.
        Index("ix_expenses_space_id_spent_on", "space_id", "spent_on"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    space_id: Mapped[int] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"))
    # Sin `ondelete` a propósito (plan 003): `NO ACTION` comprueba al final de
    # la sentencia, así que borrar el espacio quita categorías y gastos a la
    # vez sin chocar. `CASCADE` borraría gastos el día que se borren
    # categorías (principio 8), y `RESTRICT`, que comprueba fila a fila,
    # podría frenar el borrado del espacio.
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    # Salir del espacio solo borra la membresía: el gasto conserva su autor
    # (RF-20).
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # Unidad mínima de la moneda (principio 6). El tope de un billón no cabe
    # en un entero de 32 bits.
    amount: Mapped[int] = mapped_column(BigInteger)
    payment_type: Mapped[str] = mapped_column(String(6))
    # Día calendario sin hora ni zona: "hoy" se calcula en `TZ` (ADR 0007).
    spent_on: Mapped[date] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


class Budget(Base):
    """Presupuesto de una categoría desde un periodo en adelante (spec 004).

    Cada fila es un cambio, no un mes: rige desde `starts_on` hasta el
    siguiente cambio de la misma categoría (decisión 1). Una fila con
    `amount` nulo deja la categoría sin presupuesto desde ese periodo
    (decisión 4).
    """

    __tablename__ = "budgets"
    __table_args__ = (
        # No existe el presupuesto cero: "sin presupuesto" es nulo (RF-7).
        CheckConstraint(
            "amount IS NULL OR amount > 0", name="ck_budgets_amount_positive"
        ),
        # Un solo cambio por categoría y periodo, aunque lleguen dos
        # peticiones a la vez (RF-5). Su índice, que empieza por `space_id`,
        # también sirve para leer los presupuestos del espacio en el resumen.
        UniqueConstraint("space_id", "category_id", "starts_on"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    space_id: Mapped[int] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"))
    # Sin `ondelete`, por la misma razón que en `Expense` (plan 003).
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    # Siempre el día 1 del periodo; solo lo escribe la API (plan 004).
    starts_on: Mapped[date] = mapped_column(Date)
    amount: Mapped[int | None] = mapped_column(BigInteger)
    # Cuándo se fijó por última vez ese periodo. No es un historial.
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utc_now, onupdate=utc_now
    )
