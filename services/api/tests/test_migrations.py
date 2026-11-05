"""Migraciones con Alembic (spec 008, RF-31 a RF-37).

Cada test usa una base SQLite en un archivo propio: las migraciones abren y
cierran conexiones, y una base en memoria se perdería entre una y otra.
"""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db import MigrationError, build_engine, run_migrations
from app.models import Base
from tests import old_schemas

HEAD = "0002"


@pytest.fixture
def file_engine(tmp_path) -> Iterator[Engine]:
    engine = build_engine(f"sqlite:///{tmp_path / 'gastito.db'}")
    yield engine
    engine.dispose()


def execute(engine: Engine, statements: list[str]) -> None:
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def schema_diff(engine: Engine) -> list:
    """Diferencias entre la base y los modelos; vacía si coinciden (RF-36)."""
    with engine.connect() as connection:
        return compare_metadata(MigrationContext.configure(connection), Base.metadata)


def version(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def snapshot(engine: Engine, columns: dict[str, list[str]]) -> dict[str, list]:
    """Filas de cada tabla, solo con las columnas indicadas y en orden de `id`.

    Se leen las columnas que tenía la tabla antes de migrar: una columna nueva
    no cuenta como dato cambiado.
    """
    with engine.connect() as connection:
        return {
            table: connection.execute(
                text(f"SELECT {', '.join(names)} FROM {table} ORDER BY id")
            ).all()
            for table, names in columns.items()
        }


def preserved_columns(engine: Engine) -> dict[str, list[str]]:
    inspector = inspect(engine)
    return {
        table: [column["name"] for column in inspector.get_columns(table)]
        for table in old_schemas.PRESERVED_TABLES
    }


# --- Base vacía (RF-31, RF-36) ---


def test_an_empty_database_ends_with_the_schema_of_the_models(
    file_engine: Engine,
) -> None:
    run_migrations(file_engine)

    assert version(file_engine) == HEAD
    assert schema_diff(file_engine) == []
    assert not tables(file_engine) & old_schemas.TELEGRAM_TABLES


def test_migrating_twice_changes_nothing(file_engine: Engine) -> None:
    run_migrations(file_engine)
    execute(file_engine, old_schemas.BASE_ROWS)
    columns = preserved_columns(file_engine)
    before = snapshot(file_engine, columns)

    run_migrations(file_engine)

    assert version(file_engine) == HEAD
    assert snapshot(file_engine, columns) == before
    assert schema_diff(file_engine) == []


# --- Bases creadas con `create_all`, sin Alembic (RF-32, RF-34, RF-35) ---


def test_a_database_from_the_007_is_adopted_without_losing_data(
    file_engine: Engine,
) -> None:
    # Una base en uso que viene de la 005: datos, presupuestos y las tablas
    # del bot con filas, sin `alembic_version`.
    execute(
        file_engine,
        old_schemas.SCHEMA_007
        + old_schemas.BASE_ROWS
        + old_schemas.BUDGET_ROWS
        + old_schemas.TELEGRAM_ROWS,
    )
    columns = preserved_columns(file_engine)
    before = snapshot(file_engine, columns)
    assert version(file_engine) is None

    run_migrations(file_engine)

    assert version(file_engine) == HEAD
    assert snapshot(file_engine, columns) == before
    assert not tables(file_engine) & old_schemas.TELEGRAM_TABLES
    assert schema_diff(file_engine) == []


def test_existing_categories_stay_active_and_expenses_unplanned(
    file_engine: Engine,
) -> None:
    # La 0002 solo añade (plan 008, expandir): toda categoría que ya existía
    # queda activa y todo gasto queda sin rubro (RF-33, RF-39).
    execute(file_engine, old_schemas.SCHEMA_007 + old_schemas.BASE_ROWS)

    run_migrations(file_engine)

    with file_engine.connect() as connection:
        deleted = connection.execute(text("SELECT deleted_at FROM categories")).all()
        items = connection.execute(text("SELECT budget_item_id FROM expenses")).all()
    assert deleted == [(None,)]
    assert items == [(None,)]


def test_a_database_from_the_003_gets_the_tables_it_lacks(
    file_engine: Engine,
) -> None:
    execute(file_engine, old_schemas.SCHEMA_003 + old_schemas.BASE_ROWS)
    columns = preserved_columns(file_engine)
    before = snapshot(file_engine, columns)

    run_migrations(file_engine)

    assert version(file_engine) == HEAD
    assert snapshot(file_engine, columns) == before
    assert schema_diff(file_engine) == []


# --- Fallos (RF-37) ---


def test_a_failing_migration_names_it_and_stops(
    file_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_upgrade(_config: object, revision: str) -> None:
        raise RuntimeError("tabla rota")

    monkeypatch.setattr(command, "upgrade", broken_upgrade)

    with pytest.raises(MigrationError, match="0001") as error:
        run_migrations(file_engine)

    assert "tabla rota" in str(error.value)
    assert version(file_engine) is None


def test_the_api_does_not_start_if_a_migration_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    import app.main

    def failing(_engine: Engine) -> None:
        raise MigrationError("Falló la migración 0001: tabla rota")

    monkeypatch.setattr(app.main, "run_migrations", failing)

    # `with` ejecuta el `lifespan`, que es donde la API migra al arrancar.
    with pytest.raises(MigrationError), TestClient(app.main.app):
        pass


def test_the_copied_expenses_table_keeps_its_constraints(file_engine: Engine) -> None:
    # En SQLite, la 0002 copia `expenses` para añadir la clave foránea (modo
    # batch). `compare_metadata` no compara las CHECK, así que se prueban:
    # la copia debe seguir rechazando montos y tipos inválidos, y borrar el
    # espacio debe seguir borrando sus gastos.
    execute(file_engine, old_schemas.SCHEMA_007 + old_schemas.BASE_ROWS)
    run_migrations(file_engine)
    insert = (
        "INSERT INTO expenses (space_id, category_id, created_by, amount,"
        " payment_type, spent_on, created_at)"
        " VALUES (1, 1, 1, {amount}, '{payment_type}', '2026-09-16',"
        " '2026-09-16 10:00:00')"
    )

    for amount, payment_type in ((0, "debit"), (20000, "cash")):
        with pytest.raises(IntegrityError):
            execute(
                file_engine, [insert.format(amount=amount, payment_type=payment_type)]
            )
    with pytest.raises(IntegrityError):
        execute(file_engine, ["UPDATE expenses SET budget_item_id = 999 WHERE id = 1"])
    execute(file_engine, ["DELETE FROM spaces WHERE id = 1"])

    with file_engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM expenses")) == 0
