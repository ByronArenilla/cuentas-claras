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

HEAD = "0004"


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


# --- Presupuestos de la 004 convertidos en rubros (RF-33, RF-35) ---


def rows(engine: Engine, query: str) -> list:
    with engine.connect() as connection:
        return connection.execute(text(query)).all()


def test_each_budget_with_an_amount_becomes_an_item_of_its_month(
    file_engine: Engine,
) -> None:
    # Criterio 8: 400.000 para Comida desde 2026-09, y quitado desde 2026-12.
    execute(
        file_engine,
        old_schemas.SCHEMA_007 + old_schemas.BASE_ROWS + old_schemas.BUDGET_ROWS,
    )
    columns = preserved_columns(file_engine)
    before = snapshot(file_engine, columns)

    run_migrations(file_engine)

    items = rows(
        file_engine,
        "SELECT space_id, period_start, name, name_key, category_id, amount,"
        " created_at FROM budget_items",
    )
    assert items == [
        (1, "2026-09-01", "Comida", "comida", 1, 400000, "2026-09-01 10:00:00")
    ]
    # La fila que quitaba el presupuesto no crea nada.
    assert rows(file_engine, "SELECT budget_item_id FROM expenses") == [(None,)]
    assert "budgets" not in tables(file_engine)
    assert snapshot(file_engine, columns) == before
    assert schema_diff(file_engine) == []


def test_budgets_of_several_spaces_and_categories_are_all_converted(
    file_engine: Engine,
) -> None:
    execute(
        file_engine,
        old_schemas.SCHEMA_007
        + old_schemas.BASE_ROWS
        + [
            "INSERT INTO spaces (id, name, created_at)"
            " VALUES (2, 'Casa', '2026-09-01 10:00:00')",
            "INSERT INTO categories (id, space_id, name, name_key, created_at)"
            " VALUES (2, 1, 'Acción', 'accion', '2026-09-01 10:00:00')",
            "INSERT INTO categories (id, space_id, name, name_key, created_at)"
            " VALUES (3, 2, 'Comida', 'comida', '2026-09-01 10:00:00')",
            "INSERT INTO budgets (space_id, category_id, starts_on, amount,"
            " updated_at) VALUES (1, 1, '2026-10-01', 500000, '2026-10-01 10:00:00')",
            "INSERT INTO budgets (space_id, category_id, starts_on, amount,"
            " updated_at) VALUES (1, 2, '2026-10-01', 90000, '2026-10-01 10:00:00')",
            "INSERT INTO budgets (space_id, category_id, starts_on, amount,"
            " updated_at) VALUES (2, 3, '2026-10-01', 700000, '2026-10-01 10:00:00')",
        ],
    )

    run_migrations(file_engine)

    assert rows(
        file_engine,
        "SELECT space_id, period_start, name, category_id, amount FROM budget_items"
        " ORDER BY space_id, category_id",
    ) == [
        (1, "2026-10-01", "Comida", 1, 500000),
        (1, "2026-10-01", "Acción", 2, 90000),
        (2, "2026-10-01", "Comida", 3, 700000),
    ]


def test_a_database_without_budgets_converts_nothing(file_engine: Engine) -> None:
    # Una base de la 003: la 0001 crea `budgets` vacía y la 0003 la quita.
    execute(file_engine, old_schemas.SCHEMA_003 + old_schemas.BASE_ROWS)

    run_migrations(file_engine)

    assert rows(file_engine, "SELECT COUNT(*) FROM budget_items") == [(0,)]
    assert "budgets" not in tables(file_engine)


# --- Tarjetas y cuotas (spec 009, RF-45) ---


def test_existing_expenses_stay_without_card(file_engine: Engine) -> None:
    # Criterio 11 de la 009: los gastos a crédito y a débito que ya existían
    # quedan iguales y sin tarjeta (decisión 8).
    execute(
        file_engine,
        old_schemas.SCHEMA_007
        + old_schemas.BASE_ROWS
        + [
            "INSERT INTO expenses (id, space_id, category_id, created_by, amount,"
            " payment_type, spent_on, description, created_at)"
            " VALUES (2, 1, 1, 1, 90000, 'credit', '2026-10-02', NULL,"
            " '2026-10-02 18:00:00')"
        ],
    )
    columns = preserved_columns(file_engine)
    before = snapshot(file_engine, columns)

    run_migrations(file_engine)

    assert snapshot(file_engine, columns) == before
    assert rows(
        file_engine,
        "SELECT id, payment_type, card_id, installments, first_due_start"
        " FROM expenses ORDER BY id",
    ) == [(1, "debit", None, None, None), (2, "credit", None, None, None)]
    assert {"cards", "card_statements", "prepayments"} <= tables(file_engine)
    assert schema_diff(file_engine) == []


def test_the_expenses_table_checks_the_shape_of_a_card_purchase(
    file_engine: Engine,
) -> None:
    # `compare_metadata` no compara las CHECK: se prueba que la copia de
    # `expenses` que hace la 0004 en SQLite rechaza una compra mal formada.
    execute(file_engine, old_schemas.SCHEMA_007 + old_schemas.BASE_ROWS)
    run_migrations(file_engine)
    execute(
        file_engine,
        [
            "INSERT INTO cards (id, space_id, name, name_key, cutoff_day, due_day,"
            " created_at) VALUES (1, 1, 'Visa', 'visa', 25, 10, '2026-11-01 10:00:00')"
        ],
    )
    insert = (
        "INSERT INTO expenses (space_id, category_id, created_by, amount,"
        " payment_type, spent_on, created_at, card_id, installments,"
        " first_due_start) VALUES (1, 1, 1, 20000, '{payment_type}', '2026-11-12',"
        " '2026-11-12 10:00:00', 1, {installments}, '2026-12-01')"
    )

    for payment_type, installments in (("debit", 1), ("credit", 49)):
        with pytest.raises(IntegrityError):
            execute(
                file_engine,
                [insert.format(payment_type=payment_type, installments=installments)],
            )
    execute(file_engine, [insert.format(payment_type="credit", installments=6)])
    assert rows(file_engine, "SELECT COUNT(*) FROM expenses") == [(2,)]
