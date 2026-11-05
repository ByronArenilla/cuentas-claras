"""Motor, sesiones y migraciones de SQLAlchemy.

SQLite ignora las claves foráneas salvo que cada conexión las active con
`PRAGMA foreign_keys=ON`; sin eso, `ON DELETE CASCADE` y las referencias
entre tablas serían decorativas (RF-23, RF-27).
"""

from collections.abc import Iterator
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, event, make_url
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry, StaticPool

from app.config import settings


def _enable_sqlite_foreign_keys(
    dbapi_connection: DBAPIConnection, _record: ConnectionPoolEntry
) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def build_engine(database_url: str) -> Engine:
    """Crea el motor; con SQLite, activa las claves foráneas en cada conexión."""
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        return create_engine(url)

    # FastAPI atiende las rutas síncronas en varios hilos: la conexión no puede
    # quedar atada al hilo que la abrió.
    options: dict = {"connect_args": {"check_same_thread": False}}
    if url.database in (None, "", ":memory:"):
        # Cada conexión en memoria sería una base de datos distinta y vacía:
        # StaticPool reutiliza una sola para que todas vean las mismas tablas.
        options["poolclass"] = StaticPool
    engine = create_engine(url, **options)
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


# Dentro del paquete `app`: viaja con el código (plan 008).
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class MigrationError(RuntimeError):
    """Una migración falló; el mensaje dice cuál (RF-37)."""


def alembic_config() -> Config:
    """Configuración de Alembic armada en código: la API no lee alembic.ini."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


def pending_revisions(engine: Engine, config: Config) -> list[str]:
    """Revisiones que faltan por aplicar, de la más antigua a la más nueva.

    Una base sin `alembic_version` (vacía o creada con `create_all`) está en
    "ninguna", así que le faltan todas, empezando por la 0001 (RF-32).
    """
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    script = ScriptDirectory.from_config(config)
    # `iterate_revisions` va de la más nueva a la actual (sin incluirla).
    newest_first = script.iterate_revisions("head", current)
    return [revision.revision for revision in reversed(list(newest_first))]


def run_migrations(engine: Engine) -> None:
    """Aplica las migraciones pendientes (RF-31). Sin pendientes, no hace nada
    (RF-37).

    Va una por una, cada una en su transacción, para que el error diga cuál
    falló. Si una falla, la excepción sube y la API no arranca (RF-37). Las
    anteriores quedan aplicadas; la que falló se deshace hasta donde SQLite
    lo permite (plan 008, riesgos).
    """
    config = alembic_config()
    for revision in pending_revisions(engine, config):
        try:
            with engine.begin() as connection:
                # Receta de Alembic para compartir la conexión: env.py la usa
                # en lugar de crear otra (app/migrations/env.py).
                config.attributes["connection"] = connection
                command.upgrade(config, revision)
        except Exception as error:
            raise MigrationError(
                f"Falló la migración {revision}: {error}. La API no arranca. "
                "Si la base de datos quedó a medias, restaura la copia."
            ) from error


engine = build_engine(settings.database_url)
SessionLocal = sessionmaker(engine)


def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión por petición, cerrada al terminar."""
    with SessionLocal() as db:
        yield db
