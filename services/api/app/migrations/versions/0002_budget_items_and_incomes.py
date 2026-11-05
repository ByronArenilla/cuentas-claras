"""Rubros, ingresos, gasto con rubro y categorías eliminadas (spec 008).

Revisión: 0002
Anterior: 0001

Paso "expandir" del plan: solo añade. Ningún dato cambia, toda categoría
queda activa y todo gasto queda sin rubro (no planeado). La conversión del
presupuesto de la 004 llega en la 0003.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "budget_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("space_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("name_key", sa.String(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount > 0", name="ck_budget_items_amount_positive"),
        sa.UniqueConstraint(
            "space_id", "period_start", "name_key", name="uq_budget_items_name"
        ),
        sa.ForeignKeyConstraint(["space_id"], ["spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
    )
    op.create_table(
        "incomes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("space_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("name_key", sa.String(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount > 0", name="ck_incomes_amount_positive"),
        sa.UniqueConstraint(
            "space_id", "period_start", "name_key", name="uq_incomes_name"
        ),
        sa.ForeignKeyConstraint(["space_id"], ["spaces.id"], ondelete="CASCADE"),
    )

    # Una columna nula sin más: SQLite la añade con ALTER TABLE, sin copiar la
    # tabla. Copiar `categories` sería peligroso: con las claves foráneas
    # activas, borrar la tabla vieja chocaría con los gastos que la usan.
    with op.batch_alter_table("categories") as batch:
        batch.add_column(sa.Column("deleted_at", sa.DateTime(), nullable=True))

    # Añadir una clave foránea sí obliga a SQLite a copiar `expenses` (modo
    # batch). Ninguna tabla apunta a `expenses`, así que borrar la vieja no
    # choca con nada.
    with op.batch_alter_table("expenses") as batch:
        batch.add_column(sa.Column("budget_item_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_expenses_budget_item_id",
            "budget_items",
            ["budget_item_id"],
            ["id"],
        )
        batch.create_index("ix_expenses_budget_item_id", ["budget_item_id"])


def downgrade() -> None:
    # Las migraciones no se deshacen: la vuelta atrás es restaurar la copia de
    # la base de datos (spec 008, RF-38; ADR 0011).
    raise NotImplementedError("Restaura la copia de la base de datos.")
