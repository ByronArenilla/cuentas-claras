"""Gasto del mes con tarjeta o deuda (spec 010).

Revisión: 0005
Anterior: 0004

Añade `expenses.is_debt` y marca como deuda toda compra con tarjeta que ya
existe, como la trataba la 009: ningún resumen cambia (RF-12, decisión 9).
Después reemplaza la CHECK de la forma de una compra con tarjeta.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Copiada y no importada de `app.models`: una migración queda fija aunque el
# modelo cambie después (plan 008).
CARD_PURCHASE_CHECK = (
    "(card_id IS NULL AND installments IS NULL AND first_due_start IS NULL"
    " AND is_debt IS NULL)"
    " OR (card_id IS NOT NULL AND payment_type = 'credit'"
    " AND installments IS NOT NULL AND installments BETWEEN 1 AND 48"
    " AND first_due_start IS NOT NULL AND is_debt IS NOT NULL"
    " AND (is_debt OR installments = 1)"
    " AND (budget_item_id IS NULL OR NOT is_debt))"
)


def upgrade() -> None:
    # Una columna nula sin más: SQLite la añade sin copiar la tabla, y la
    # CHECK vieja no la menciona.
    with op.batch_alter_table("expenses") as batch:
        batch.add_column(sa.Column("is_debt", sa.Boolean(), nullable=True))

    # Antes de la CHECK nueva, que exige el valor en toda compra con tarjeta.
    op.execute("UPDATE expenses SET is_debt = true WHERE card_id IS NOT NULL")

    # Reemplazar una CHECK obliga a SQLite a copiar `expenses` (modo batch).
    with op.batch_alter_table("expenses") as batch:
        batch.drop_constraint("ck_expenses_card_purchase", type_="check")
        batch.create_check_constraint("ck_expenses_card_purchase", CARD_PURCHASE_CHECK)


def downgrade() -> None:
    # Las migraciones no se deshacen: la vuelta atrás es restaurar la copia de
    # la base de datos (spec 008, RF-38; ADR 0011).
    raise NotImplementedError("Restaura la copia de la base de datos.")
