"""Esquema al cerrar la spec 007, para adoptar bases creadas con `create_all`.

Revisión: 0001
Anterior: ninguna

Es idempotente: crea cada tabla solo si no existe (spec 008, RF-32). Así
sirve igual para:

- una base vacía, que recibe todas las tablas;
- una base creada con `create_all` en la 007, que no recibe ninguna;
- una base de una spec anterior, que recibe solo las que le faltan (por
  ejemplo `budgets`, si viene de la 003).

Las tablas se escriben a mano y no desde los modelos: los modelos siguen
cambiando, y esta migración debe describir siempre el esquema de la 007.

Al final borra las tablas del bot de Telegram si existen (decisión 1 de la
007, RF-34): solo guardan vínculos de chat que ya no usa nada.

Lo que no hace: comprobar las columnas de las tablas que ya existen. Si una
tabla local tuviera otra forma, se queda así (plan 008, riesgos).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def create_if_missing(name: str, *elements: sa.SchemaItem) -> bool:
    """Crea la tabla si no existe. Devuelve si la creó."""
    if sa.inspect(op.get_bind()).has_table(name):
        return False
    op.create_table(name, *elements)
    return True


def upgrade() -> None:
    # En orden de dependencias: cada tabla después de las que referencia.
    create_if_missing(
        "spaces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    create_if_missing(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    create_if_missing(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("space_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("name_key", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("space_id", "name_key"),
        sa.ForeignKeyConstraint(["space_id"], ["spaces.id"], ondelete="CASCADE"),
    )
    create_if_missing(
        "invitations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("space_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("used_by", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash"),
        sa.ForeignKeyConstraint(["space_id"], ["spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["used_by"], ["users.id"]),
    )
    create_if_missing(
        "memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("space_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "space_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["space_id"], ["spaces.id"], ondelete="CASCADE"),
    )
    create_if_missing(
        "sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    created_expenses = create_if_missing(
        "expenses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("space_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("payment_type", sa.String(6), nullable=False),
        sa.Column("spent_on", sa.Date(), nullable=False),
        sa.Column("description", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount > 0", name="ck_expenses_amount_positive"),
        sa.CheckConstraint(
            "payment_type IN ('credit', 'debit')", name="ck_expenses_payment_type"
        ),
        sa.ForeignKeyConstraint(["space_id"], ["spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
    )
    if created_expenses:
        # Si la tabla ya existía, su índice también: los dos llegaron en la 003.
        op.create_index(
            "ix_expenses_space_id_spent_on", "expenses", ["space_id", "spent_on"]
        )
    create_if_missing(
        "budgets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("space_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "amount IS NULL OR amount > 0", name="ck_budgets_amount_positive"
        ),
        sa.UniqueConstraint("space_id", "category_id", "starts_on"),
        sa.ForeignKeyConstraint(["space_id"], ["spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
    )

    # IF EXISTS: una base nueva, o creada después de la 007, no las tiene.
    op.execute("DROP TABLE IF EXISTS telegram_chats")
    op.execute("DROP TABLE IF EXISTS telegram_link_codes")


def downgrade() -> None:
    # Las migraciones no se deshacen: la vuelta atrás es restaurar la copia de
    # la base de datos (spec 008, RF-38; ADR 0011).
    raise NotImplementedError("Restaura la copia de la base de datos.")
