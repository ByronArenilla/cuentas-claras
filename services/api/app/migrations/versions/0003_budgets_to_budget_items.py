"""Presupuestos de la 004 convertidos en rubros (spec 008, RF-33).

Revisión: 0003
Anterior: 0002

Paso "contraer" del plan: convierte los datos viejos y borra lo que sobra.

Cada fila de `budgets` con monto pasa a ser un rubro del mes desde el que
regía, con el nombre y la categoría de su categoría y el mismo monto
(decisión 4). Las filas sin monto quitaban el presupuesto desde ese mes, y en
el plan por mes eso es simplemente no tener rubro: no crean nada.

Los gastos no se tocan: la 0002 los dejó sin rubro (no planeados) y así
siguen (RF-35).

No choca con el índice único de los rubros: hay una sola fila de `budgets`
por espacio, categoría y mes, y dos categorías de un espacio nunca tienen el
mismo `name_key` (spec 002). Así que nunca salen dos rubros con el mismo
nombre en el mismo mes.

Se escribe en SQL y no con los modelos: el modelo `Budget` ya no existe.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # INSERT ... SELECT: copia en una sola sentencia, sin traer las filas a
    # Python. `created_at` del rubro es la última vez que se fijó ese
    # presupuesto.
    op.execute(
        """
        INSERT INTO budget_items
            (space_id, period_start, name, name_key, category_id, amount, created_at)
        SELECT b.space_id, b.starts_on, c.name, c.name_key, b.category_id,
               b.amount, b.updated_at
        FROM budgets AS b
        JOIN categories AS c ON c.id = b.category_id
        WHERE b.amount IS NOT NULL
        ORDER BY b.space_id, b.starts_on, b.category_id
        """
    )
    # Ninguna tabla apunta a `budgets`: se borra sin chocar con nada.
    op.drop_table("budgets")


def downgrade() -> None:
    # Las migraciones no se deshacen: la vuelta atrás es restaurar la copia de
    # la base de datos (spec 008, RF-38; ADR 0011).
    raise NotImplementedError("Restaura la copia de la base de datos.")
