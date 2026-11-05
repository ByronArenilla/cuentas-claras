"""Esquemas viejos escritos a mano, para probar las migraciones (spec 008).

Es el SQL que generaba `create_all` en SQLite antes de Alembic. No se arma
desde los modelos porque los modelos siguen cambiando: así cada test
reproduce de verdad una base de datos de antes.
"""

USERS = """CREATE TABLE users (
    id INTEGER NOT NULL,
    email VARCHAR(320) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (email)
)"""

SPACES = """CREATE TABLE spaces (
    id INTEGER NOT NULL,
    name VARCHAR(100) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id)
)"""

MEMBERSHIPS = """CREATE TABLE memberships (
    id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    space_id INTEGER NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (user_id, space_id),
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY(space_id) REFERENCES spaces (id) ON DELETE CASCADE
)"""

INVITATIONS = """CREATE TABLE invitations (
    id INTEGER NOT NULL,
    code_hash VARCHAR(64) NOT NULL,
    space_id INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    expires_at DATETIME NOT NULL,
    used_at DATETIME,
    used_by INTEGER,
    PRIMARY KEY (id),
    UNIQUE (code_hash),
    FOREIGN KEY(space_id) REFERENCES spaces (id) ON DELETE CASCADE,
    FOREIGN KEY(created_by) REFERENCES users (id),
    FOREIGN KEY(used_by) REFERENCES users (id)
)"""

SESSIONS = """CREATE TABLE sessions (
    id INTEGER NOT NULL,
    token_hash VARCHAR(64) NOT NULL,
    user_id INTEGER NOT NULL,
    expires_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (token_hash),
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)"""

CATEGORIES = """CREATE TABLE categories (
    id INTEGER NOT NULL,
    space_id INTEGER NOT NULL,
    name VARCHAR(50) NOT NULL,
    name_key VARCHAR NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (space_id, name_key),
    FOREIGN KEY(space_id) REFERENCES spaces (id) ON DELETE CASCADE
)"""

EXPENSES = [
    """CREATE TABLE expenses (
    id INTEGER NOT NULL,
    space_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    amount BIGINT NOT NULL,
    payment_type VARCHAR(6) NOT NULL,
    spent_on DATE NOT NULL,
    description VARCHAR(200),
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_expenses_amount_positive CHECK (amount > 0),
    CONSTRAINT ck_expenses_payment_type CHECK (payment_type IN ('credit', 'debit')),
    FOREIGN KEY(space_id) REFERENCES spaces (id) ON DELETE CASCADE,
    FOREIGN KEY(category_id) REFERENCES categories (id),
    FOREIGN KEY(created_by) REFERENCES users (id)
)""",
    "CREATE INDEX ix_expenses_space_id_spent_on ON expenses (space_id, spent_on)",
]

BUDGETS = """CREATE TABLE budgets (
    id INTEGER NOT NULL,
    space_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    starts_on DATE NOT NULL,
    amount BIGINT,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_budgets_amount_positive CHECK (amount IS NULL OR amount > 0),
    UNIQUE (space_id, category_id, starts_on),
    FOREIGN KEY(space_id) REFERENCES spaces (id) ON DELETE CASCADE,
    FOREIGN KEY(category_id) REFERENCES categories (id)
)"""

# Las tablas del bot tal como las dejó la 005 (retiradas en la 007).
TELEGRAM = [
    """CREATE TABLE telegram_link_codes (
    id INTEGER NOT NULL,
    code_hash VARCHAR(64) NOT NULL,
    user_id INTEGER NOT NULL,
    expires_at DATETIME NOT NULL,
    used_at DATETIME,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (code_hash),
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)""",
    """CREATE TABLE telegram_chats (
    id INTEGER NOT NULL,
    chat_id BIGINT NOT NULL,
    user_id INTEGER NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (chat_id),
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)""",
]
TELEGRAM_TABLES = {"telegram_link_codes", "telegram_chats"}

# Una base de la 003: gastos, pero todavía sin presupuestos.
SCHEMA_003 = [USERS, SPACES, MEMBERSHIPS, INVITATIONS, SESSIONS, CATEGORIES, *EXPENSES]
# Una base que viene de la 005 y llegó a la 007: la 007 no borró las tablas
# del bot (su decisión 1), así que siguen ahí.
SCHEMA_007 = [*SCHEMA_003, BUDGETS, *TELEGRAM]

# Filas mínimas de una base en uso: Ana, su espacio, una categoría y un gasto.
BASE_ROWS = [
    "INSERT INTO users (id, email, password_hash, created_at)"
    " VALUES (1, 'ana@example.com', 'hash', '2026-09-01 10:00:00')",
    "INSERT INTO spaces (id, name, created_at)"
    " VALUES (1, 'Personal', '2026-09-01 10:00:00')",
    "INSERT INTO memberships (id, user_id, space_id, created_at)"
    " VALUES (1, 1, 1, '2026-09-01 10:00:00')",
    "INSERT INTO sessions (id, token_hash, user_id, expires_at, created_at)"
    " VALUES (1, 'token', 1, '2026-09-16 10:00:00', '2026-09-01 10:00:00')",
    "INSERT INTO invitations (id, code_hash, space_id, created_by, expires_at)"
    " VALUES (1, 'invitacion', 1, 1, '2026-09-02 10:00:00')",
    "INSERT INTO categories (id, space_id, name, name_key, created_at)"
    " VALUES (1, 1, 'Comida', 'comida', '2026-09-01 10:00:00')",
    "INSERT INTO expenses (id, space_id, category_id, created_by, amount,"
    " payment_type, spent_on, description, created_at)"
    " VALUES (1, 1, 1, 1, 20000, 'debit', '2026-09-15', 'Mercado',"
    " '2026-09-15 18:00:00')",
]
BUDGET_ROWS = [
    # 400.000 para Comida desde septiembre, y sin presupuesto desde diciembre.
    "INSERT INTO budgets (id, space_id, category_id, starts_on, amount, updated_at)"
    " VALUES (1, 1, 1, '2026-09-01', 400000, '2026-09-01 10:00:00')",
    "INSERT INTO budgets (id, space_id, category_id, starts_on, amount, updated_at)"
    " VALUES (2, 1, 1, '2026-12-01', NULL, '2026-11-20 10:00:00')",
]
TELEGRAM_ROWS = [
    "INSERT INTO telegram_link_codes (code_hash, user_id, expires_at, created_at)"
    " VALUES ('h', 1, '2026-11-04 10:10:00', '2026-11-04 10:00:00')",
    "INSERT INTO telegram_chats (chat_id, user_id, created_at)"
    " VALUES (4503599627370495, 1, '2026-11-04 10:01:00')",
]
# Tablas cuyas filas ninguna migración puede tocar (RF-35).
PRESERVED_TABLES = (
    "users",
    "spaces",
    "memberships",
    "invitations",
    "sessions",
    "categories",
    "expenses",
)
