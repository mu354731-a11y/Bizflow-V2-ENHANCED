
import os
from pathlib import Path

from sqlalchemy import create_engine, text


# --------------------------------------------------
# DATABASE CONNECTION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{BASE_DIR / 'bizflow.db'}"
)

# Support common PostgreSQL connection-string formats.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://", "postgresql+psycopg://", 1
    )
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://", "postgresql+psycopg://", 1
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    future=True
)

IS_SQLITE = DATABASE_URL.startswith("sqlite")
ID_COLUMN = (
    "INTEGER PRIMARY KEY AUTOINCREMENT"
    if IS_SQLITE
    else "SERIAL PRIMARY KEY"
)


# --------------------------------------------------
# DATABASE TABLES
# --------------------------------------------------

SCHEMA = [
    f"""
    CREATE TABLE IF NOT EXISTS businesses (
        id {ID_COLUMN},
        name VARCHAR(200) NOT NULL,
        owner VARCHAR(200),
        phone VARCHAR(50),
        email VARCHAR(200),
        address TEXT,
        tax_id VARCHAR(100),
        currency VARCHAR(10) DEFAULT 'PKR',
        created_at TEXT
    )
    """,

    f"""
    CREATE TABLE IF NOT EXISTS users (
        id {ID_COLUMN},
        business_id INTEGER NOT NULL,
        username VARCHAR(100) NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        full_name VARCHAR(200) NOT NULL,
        role VARCHAR(30) NOT NULL DEFAULT 'owner',
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT,
        FOREIGN KEY (business_id) REFERENCES businesses(id)
    )
    """,

    f"""
    CREATE TABLE IF NOT EXISTS customers (
        id {ID_COLUMN},
        business_id INTEGER NOT NULL,
        name VARCHAR(200) NOT NULL,
        phone VARCHAR(50),
        email VARCHAR(200),
        address TEXT,
        notes TEXT,
        created_at TEXT,
        FOREIGN KEY (business_id) REFERENCES businesses(id)
    )
    """,

    f"""
    CREATE TABLE IF NOT EXISTS products (
        id {ID_COLUMN},
        business_id INTEGER NOT NULL,
        name VARCHAR(200) NOT NULL,
        sku VARCHAR(100),
        category VARCHAR(100),
        cost FLOAT NOT NULL DEFAULT 0,
        price FLOAT NOT NULL DEFAULT 0,
        stock INTEGER NOT NULL DEFAULT 0,
        low_stock_limit INTEGER NOT NULL DEFAULT 5,
        created_at TEXT,
        FOREIGN KEY (business_id) REFERENCES businesses(id)
    )
    """,

    f"""
    CREATE TABLE IF NOT EXISTS invoices (
        id {ID_COLUMN},
        business_id INTEGER NOT NULL,
        number VARCHAR(100) NOT NULL,
        customer_id INTEGER,
        customer_name VARCHAR(200) NOT NULL,
        phone VARCHAR(50),
        invoice_date TEXT NOT NULL,
        due_date TEXT,
        subtotal FLOAT NOT NULL DEFAULT 0,
        discount FLOAT NOT NULL DEFAULT 0,
        total FLOAT NOT NULL DEFAULT 0,
        paid FLOAT NOT NULL DEFAULT 0,
        status VARCHAR(30) NOT NULL DEFAULT 'Unpaid',
        notes TEXT,
        created_by INTEGER,
        created_at TEXT,
        FOREIGN KEY (business_id) REFERENCES businesses(id),
        FOREIGN KEY (customer_id) REFERENCES customers(id),
        FOREIGN KEY (created_by) REFERENCES users(id),
        UNIQUE (business_id, number)
    )
    """,

    f"""
    CREATE TABLE IF NOT EXISTS invoice_items (
        id {ID_COLUMN},
        business_id INTEGER NOT NULL,
        invoice_id INTEGER NOT NULL,
        product_id INTEGER,
        description TEXT NOT NULL,
        quantity FLOAT NOT NULL DEFAULT 1,
        unit_price FLOAT NOT NULL DEFAULT 0,
        unit_cost FLOAT NOT NULL DEFAULT 0,
        line_total FLOAT NOT NULL DEFAULT 0,
        FOREIGN KEY (business_id) REFERENCES businesses(id),
        FOREIGN KEY (invoice_id) REFERENCES invoices(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    """,

    f"""
    CREATE TABLE IF NOT EXISTS payments (
        id {ID_COLUMN},
        business_id INTEGER NOT NULL,
        invoice_id INTEGER NOT NULL,
        amount FLOAT NOT NULL DEFAULT 0,
        payment_date TEXT NOT NULL,
        method VARCHAR(100),
        reference TEXT,
        created_by INTEGER,
        created_at TEXT,
        FOREIGN KEY (business_id) REFERENCES businesses(id),
        FOREIGN KEY (invoice_id) REFERENCES invoices(id),
        FOREIGN KEY (created_by) REFERENCES users(id)
    )
    """,

    f"""
    CREATE TABLE IF NOT EXISTS expenses (
        id {ID_COLUMN},
        business_id INTEGER NOT NULL,
        category VARCHAR(100),
        description TEXT,
        amount FLOAT NOT NULL DEFAULT 0,
        expense_date TEXT NOT NULL,
        payment_method VARCHAR(100),
        created_by INTEGER,
        created_at TEXT,
        FOREIGN KEY (business_id) REFERENCES businesses(id),
        FOREIGN KEY (created_by) REFERENCES users(id)
    )
    """,

    # Persistent login sessions
    f"""
    CREATE TABLE IF NOT EXISTS login_sessions (
        token_hash VARCHAR(64) PRIMARY KEY,
        user_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """,

    # Helpful indexes
    """
    CREATE INDEX IF NOT EXISTS idx_users_business
    ON users(business_id)
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_customers_business
    ON customers(business_id)
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_products_business
    ON products(business_id)
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_invoices_business_date
    ON invoices(business_id, invoice_date)
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_expenses_business_date
    ON expenses(business_id, expense_date)
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_payments_invoice
    ON payments(business_id, invoice_id)
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_login_sessions_user
    ON login_sessions(user_id)
    """,
]


# --------------------------------------------------
# INITIALIZE DATABASE
# --------------------------------------------------

def init_db():
    """Create missing tables and indexes without deleting existing data."""
    with engine.begin() as connection:
        if IS_SQLITE:
            connection.execute(text("PRAGMA foreign_keys = ON"))

        for statement in SCHEMA:
            connection.execute(text(statement))


# --------------------------------------------------
# GENERAL DATABASE HELPERS
# --------------------------------------------------

def execute(sql, params=None):
    """
    Run an INSERT, UPDATE, or DELETE statement.

    Returns the new business ID when inserting a business.
    Otherwise returns the affected row count.
    """
    params = params or {}
    statement = sql.strip()
    normalized = statement.lower()

    # signup() needs the newly created business ID.
    if (
        normalized.startswith("insert into businesses")
        and " returning " not in normalized
    ):
        statement = statement.rstrip().rstrip(";") + " RETURNING id"

        with engine.begin() as connection:
            result = connection.execute(text(statement), params)
            row = result.fetchone()
            return row[0] if row else None

    with engine.begin() as connection:
        result = connection.execute(text(statement), params)

        # Return the ID if a caller explicitly requests RETURNING.
        if " returning " in normalized:
            row = result.fetchone()
            return row[0] if row else None

        return result.rowcount


def query(sql, params=None):
    """Run a SELECT query and return rows as dictionaries."""
    params = params or {}

    with engine.connect() as connection:
        result = connection.execute(text(sql), params)
        return [dict(row) for row in result.mappings().all()]


def business_query(sql, business_id, params=None):
    """Run a query with a business ID available as parameter b."""
    values = dict(params or {})
    values["b"] = business_id
    return query(sql, values)


def business_execute(sql, business_id, params=None):
    """Run a write query with a business ID available as parameter b."""
    values = dict(params or {})
    values["b"] = business_id
    return execute(sql, values)
