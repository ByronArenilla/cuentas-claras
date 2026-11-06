"""Tablas de usuarios, espacios, membresías, invitaciones, sesiones, categorías,
gastos, rubros, ingresos, tarjetas, abonos y valores del extracto."""

import unicodedata
from datetime import UTC, date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
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
    # Nula si está activa. Eliminar una categoría la archiva en lugar de
    # borrarla: sus rubros y gastos la conservan (spec 008, decisión 14).
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    @validates("name")
    def _fill_name_key(self, _key: str, name: str) -> str:
        """Recalcula `name_key` cada vez que se asigna el nombre: así las dos
        columnas no pueden quedar desalineadas (plan 002)."""
        self.name_key = category_key(name)
        return name


# Forma de una compra con tarjeta (specs 009 y 010). La comparte la migración
# 0005, que la crea en las bases existentes.
CARD_PURCHASE_CHECK = (
    "(card_id IS NULL AND installments IS NULL AND first_due_start IS NULL"
    " AND is_debt IS NULL)"
    " OR (card_id IS NOT NULL AND payment_type = 'credit'"
    " AND installments IS NOT NULL AND installments BETWEEN 1 AND 48"
    " AND first_due_start IS NOT NULL AND is_debt IS NOT NULL"
    " AND (is_debt OR installments = 1)"
    " AND (budget_item_id IS NULL OR NOT is_debt))"
)


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
        # Para cambiar o soltar los gastos de un rubro (RF-7, RF-8 de la
        # 008). PostgreSQL no indexa solas las claves foráneas.
        Index("ix_expenses_budget_item_id", "budget_item_id"),
        # Una compra con tarjeta (spec 009) es a crédito, con 1 a 48 cuotas,
        # su mes de pago y la marca de deuda (spec 010); un gasto sin tarjeta
        # no tiene ninguno de esos datos. A varias cuotas es deuda, y solo un
        # gasto del mes (no deuda) puede tener rubro. Última defensa si algo
        # salta la validación. `IS NOT NULL` explícito: `NULL BETWEEN 1 AND
        # 48` da NULL, y una CHECK que da NULL se considera cumplida.
        CheckConstraint(
            CARD_PURCHASE_CHECK,
            name="ck_expenses_card_purchase",
        ),
        # Deudas busca las compras de cada tarjeta en una ventana de meses, y
        # el estado, todas las de una tarjeta (plan 009).
        Index("ix_expenses_card_id_first_due_start", "card_id", "first_due_start"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    space_id: Mapped[int] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"))
    # Sin `ondelete` a propósito (plan 003): `NO ACTION` comprueba al final de
    # la sentencia, así que borrar el espacio quita categorías y gastos a la
    # vez sin chocar. `CASCADE` borraría gastos el día que se borren
    # categorías (principio 8), y `RESTRICT`, que comprueba fila a fila,
    # podría frenar el borrado del espacio.
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    # Rubro del gasto; nulo si no estaba planeado (spec 008). Si tiene rubro,
    # `category_id` es la del rubro: la API mantiene las dos de acuerdo
    # (decisión 5). Sin `ondelete`, por la misma razón que `category_id`.
    budget_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("budget_items.id", name="fk_expenses_budget_item_id")
    )
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
    # Compra con tarjeta (spec 009): tarjeta, número de cuotas y mes de pago de
    # la primera cuota (día 1). Los tres son nulos en un gasto sin tarjeta.
    # Sin `ondelete`: una tarjeta nunca se borra, se archiva (decisión 9).
    card_id: Mapped[int | None] = mapped_column(
        ForeignKey("cards.id", name="fk_expenses_card_id")
    )
    installments: Mapped[int | None] = mapped_column(SmallInteger)
    # Se guarda al registrar: si el banco cambia los días de la tarjeta, las
    # compras ya registradas no cambian de mes (decisión 13).
    first_due_start: Mapped[date | None] = mapped_column(Date)
    # Spec 010: en una compra con tarjeta, verdadero si es deuda (llega a
    # Deudas en los meses de pago) y falso si es un gasto del mes (cuenta el
    # mes de la compra, como un débito). Nulo sin tarjeta.
    is_debt: Mapped[bool | None] = mapped_column(Boolean)


class BudgetItem(Base):
    """Rubro: una línea del plan de un mes, con nombre libre, categoría y
    monto planeado (spec 008). Cada mes tiene los suyos (decisión 1)."""

    __tablename__ = "budget_items"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_budget_items_amount_positive"),
        # Dos rubros del mismo mes no se llaman igual, aunque lleguen dos
        # peticiones o dos copias a la vez (RF-3, RF-14). Su índice, que
        # empieza por espacio y mes, sirve también para leer el plan del mes.
        UniqueConstraint(
            "space_id", "period_start", "name_key", name="uq_budget_items_name"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    space_id: Mapped[int] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"))
    # Siempre el día 1 del periodo; solo lo escribe la API y no cambia
    # (decisión 12).
    period_start: Mapped[date] = mapped_column(Date)
    name: Mapped[str] = mapped_column(String(50))
    # Misma comparación que las categorías (decisión 22, ADR 0006).
    name_key: Mapped[str] = mapped_column(String)
    # Sin `ondelete`, por la misma razón que en `Expense` (plan 003).
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    amount: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)

    @validates("name")
    def _fill_name_key(self, _key: str, name: str) -> str:
        self.name_key = category_key(name)
        return name


class Income(Base):
    """Ingreso que el espacio espera recibir en un mes (spec 008, decisión 3).
    Es parte del plan: nombre y monto, sin fecha."""

    __tablename__ = "incomes"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_incomes_amount_positive"),
        UniqueConstraint(
            "space_id", "period_start", "name_key", name="uq_incomes_name"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    space_id: Mapped[int] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"))
    period_start: Mapped[date] = mapped_column(Date)
    name: Mapped[str] = mapped_column(String(50))
    name_key: Mapped[str] = mapped_column(String)
    amount: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)

    @validates("name")
    def _fill_name_key(self, _key: str, name: str) -> str:
        self.name_key = category_key(name)
        return name


class Card(Base):
    """Tarjeta de crédito del espacio (spec 009). Eliminarla la archiva: sus
    compras, abonos y extractos la conservan (decisión 9)."""

    __tablename__ = "cards"
    __table_args__ = (
        CheckConstraint("cutoff_day BETWEEN 1 AND 31", name="ck_cards_cutoff_day"),
        CheckConstraint("due_day BETWEEN 1 AND 31", name="ck_cards_due_day"),
        CheckConstraint(
            "monthly_rate_bp IS NULL OR monthly_rate_bp BETWEEN 1 AND 1000",
            name="ck_cards_monthly_rate_bp",
        ),
        # Incluye las archivadas: crear una con el nombre de una archivada la
        # restaura, nunca hay dos con el mismo nombre (RF-2, RF-7).
        UniqueConstraint("space_id", "name_key", name="uq_cards_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    space_id: Mapped[int] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(50))
    name_key: Mapped[str] = mapped_column(String)
    cutoff_day: Mapped[int] = mapped_column(SmallInteger)
    due_day: Mapped[int] = mapped_column(SmallInteger)
    # Tasa mensual en puntos básicos: 1,89 % es 189. La API la recibe y la
    # devuelve como decimal (`1.89`); aquí es un entero porque SQLite no tiene
    # un tipo decimal exacto y guardaría un `Numeric` como `float` (plan 009).
    monthly_rate_bp: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    @validates("name")
    def _fill_name_key(self, _key: str, name: str) -> str:
        self.name_key = category_key(name)
        return name


class CardStatement(Base):
    """Valor real del extracto de una tarjeta en un mes (spec 009, RF-31).
    Reemplaza la deuda estimada de ese mes."""

    __tablename__ = "card_statements"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_card_statements_amount"),
        UniqueConstraint("card_id", "period_start", name="uq_card_statements_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    space_id: Mapped[int] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"))
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"))
    period_start: Mapped[date] = mapped_column(Date)
    amount: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utc_now, onupdate=utc_now
    )


class Prepayment(Base):
    """Abono a una compra con tarjeta en un mes, además de su cuota (spec 009,
    decisión 7). Baja la cuota (`installment`) o el plazo (`term`)."""

    __tablename__ = "prepayments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_prepayments_amount_positive"),
        CheckConstraint(
            "reduces IN ('installment', 'term')", name="ck_prepayments_reduces"
        ),
        # Un abono por compra y mes (decisión 18), aunque lleguen dos a la vez.
        UniqueConstraint("expense_id", "period_start", name="uq_prepayments_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    space_id: Mapped[int] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"))
    # Sin `ondelete`: una compra con abonos no se borra (RF-16), y borrar el
    # espacio quita gastos y abonos en la misma sentencia (plan 003).
    expense_id: Mapped[int] = mapped_column(ForeignKey("expenses.id"))
    period_start: Mapped[date] = mapped_column(Date)
    amount: Mapped[int] = mapped_column(BigInteger)
    reduces: Mapped[str] = mapped_column(String(11))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
