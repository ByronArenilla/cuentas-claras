"""Entorno de Alembic: cómo se conecta cada migración (spec 008, plan).

Alembic ejecuta este archivo en cada comando. Hay dos formas de llegar aquí:

- Desde la API (`app.db.run_migrations`): trae su propia conexión en
  `config.attributes["connection"]`, ya dentro de una transacción. Se usa tal
  cual, así las claves foráneas de SQLite siguen activas (app/db.py).
- Desde la línea de comandos (`alembic revision --autogenerate`): no trae
  conexión, así que se usa el motor de la API, configurado con `DATABASE_URL`.
"""

from alembic import context
from sqlalchemy import Connection

from app.models import Base

config = context.config


def run_migrations_with(connection: Connection) -> None:
    context.configure(
        connection=connection,
        # Los modelos: autogenerate compara la base con ellos.
        target_metadata=Base.metadata,
        # SQLite no puede añadir claves foráneas ni borrar columnas con
        # ALTER TABLE. En modo batch, Alembic copia la tabla cuando hace
        # falta; en PostgreSQL usa ALTER TABLE normal.
        # https://alembic.sqlalchemy.org/en/latest/batch.html
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    # Generar SQL sin conectarse (`--sql`) no se usa en este proyecto.
    raise RuntimeError("gastito no usa migraciones offline (--sql).")

shared_connection = config.attributes.get("connection")
if shared_connection is not None:
    run_migrations_with(shared_connection)
else:
    # Importado aquí: lee `DATABASE_URL` del entorno al importarse.
    from app.db import engine

    with engine.begin() as connection:
        run_migrations_with(connection)
