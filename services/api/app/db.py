"""Motor y sesiones de SQLAlchemy.

SQLite ignora las claves foráneas salvo que cada conexión las active con
`PRAGMA foreign_keys=ON`; sin eso, `ON DELETE CASCADE` y las referencias
entre tablas serían decorativas (RF-23, RF-27).
"""

from sqlalchemy import Engine, create_engine, event, make_url
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import sessionmaker
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


def create_all(engine: Engine) -> None:
    """Crea las tablas que falten. No altera las que ya existen."""
    from app.models import Base

    Base.metadata.create_all(engine)


engine = build_engine(settings.database_url)
SessionLocal = sessionmaker(engine)
