"""Tarjetas, compras a cuotas, abonos y valor real del extracto (spec 009).

Revisión: 0004
Anterior: 0003

Solo añade (RF-45). Ningún dato cambia: todo gasto que ya existía queda sin
tarjeta, también los gastos a crédito, que siguen contando el día del gasto
(decisión 8).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("space_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("name_key", sa.String(), nullable=False),
        sa.Column("cutoff_day", sa.SmallInteger(), nullable=False),
        sa.Column("due_day", sa.SmallInteger(), nullable=False),
        # Puntos básicos: 1,89 % es 189 (plan 009).
        sa.Column("monthly_rate_bp", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("cutoff_day BETWEEN 1 AND 31", name="ck_cards_cutoff_day"),
        sa.CheckConstraint("due_day BETWEEN 1 AND 31", name="ck_cards_due_day"),
        sa.CheckConstraint(
            "monthly_rate_bp IS NULL OR monthly_rate_bp BETWEEN 1 AND 1000",
            name="ck_cards_monthly_rate_bp",
        ),
        sa.UniqueConstraint("space_id", "name_key", name="uq_cards_name"),
        sa.ForeignKeyConstraint(["space_id"], ["spaces.id"], ondelete="CASCADE"),
    )

    # Añadir una clave foránea y una CHECK obliga a SQLite a copiar `expenses`
    # (modo batch, plan 008). Los gastos existentes cumplen la CHECK: sus tres
    # columnas nuevas quedan nulas. Se hace antes de crear `prepayments`, que
    # apunta a `expenses`: con esa tabla ya creada, borrar la `expenses` vieja
    # al copiarla chocaría con su clave foránea.
    with op.batch_alter_table("expenses") as batch:
        batch.add_column(sa.Column("card_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("installments", sa.SmallInteger(), nullable=True))
        batch.add_column(sa.Column("first_due_start", sa.Date(), nullable=True))
        batch.create_foreign_key("fk_expenses_card_id", "cards", ["card_id"], ["id"])
        batch.create_index(
            "ix_expenses_card_id_first_due_start", ["card_id", "first_due_start"]
        )
        batch.create_check_constraint(
            "ck_expenses_card_purchase",
            "(card_id IS NULL AND installments IS NULL"
            " AND first_due_start IS NULL)"
            " OR (card_id IS NOT NULL AND payment_type = 'credit'"
            " AND budget_item_id IS NULL AND installments IS NOT NULL"
            " AND installments BETWEEN 1 AND 48"
            " AND first_due_start IS NOT NULL)",
        )

    op.create_table(
        "card_statements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("space_id", sa.Integer(), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount >= 0", name="ck_card_statements_amount"),
        sa.UniqueConstraint(
            "card_id", "period_start", name="uq_card_statements_period"
        ),
        sa.ForeignKeyConstraint(["space_id"], ["spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["card_id"], ["cards.id"]),
    )
    op.create_table(
        "prepayments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("space_id", sa.Integer(), nullable=False),
        sa.Column("expense_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("reduces", sa.String(11), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount > 0", name="ck_prepayments_amount_positive"),
        sa.CheckConstraint(
            "reduces IN ('installment', 'term')", name="ck_prepayments_reduces"
        ),
        sa.UniqueConstraint("expense_id", "period_start", name="uq_prepayments_period"),
        sa.ForeignKeyConstraint(["space_id"], ["spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["expense_id"], ["expenses.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
    )


def downgrade() -> None:
    # Las migraciones no se deshacen: la vuelta atrás es restaurar la copia de
    # la base de datos (spec 008, RF-38; ADR 0011).
    raise NotImplementedError("Restaura la copia de la base de datos.")
