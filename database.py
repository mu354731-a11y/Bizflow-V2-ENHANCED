
import os
from pathlib import Path
from sqlalchemy import create_engine, text

BASE_DIR = Path(__file__).resolve().parent

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{BASE_DIR / 'bizflow.db'}"
)

engine = create_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True
)

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS businesses (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        owner TEXT DEFAULT '',
        phone TEXT DEFAULT '',
        email TEXT DEFAULT '',
        address TEXT DEFAULT '',
        tax_id TEXT DEFAULT '',
        currency TEXT DEFAULT 'PKR',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        business_id INTEGER NOT NULL,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT DEFAULT '',
        role TEXT NOT NULL DEFAULT 'owner',
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        FOREIGN KEY (business_id) REFERENCES businesses(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY,
        business_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        phone TEXT DEFAULT '',
        email TEXT DEFAULT '',
        address TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY (business_id) REFERENCES businesses(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY,
        business_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        sku TEXT DEFAULT '',
        price REAL NOT NULL DEFAULT 0,
        cost REAL NOT NULL DEFAULT 0,
        stock INTEGER NOT NULL DEFAULT 0,
        low_stock_limit INTEGER NOT NULL DEFAULT 5,
        FOREIGN KEY (business_id) REFERENCES businesses(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY,
        business_id INTEGER NOT NULL,
        number TEXT NOT NULL,
        customer_id INTEGER,
        customer_name TEXT NOT NULL,
        phone TEXT DEFAULT '',
        invoice_date TEXT NOT NULL,
        due_date TEXT DEFAULT '',
        subtotal REAL NOT NULL,
        discount REAL NOT NULL DEFAULT 0,
        total REAL NOT NULL,
        paid REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'Unpaid',
        notes TEXT DEFAULT '',
        created_by INTEGER,
        created_at TEXT NOT NULL,
        UNIQUE (business_id, number),
        FOREIGN KEY (business_id) REFERENCES businesses(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invoice_items (
        id INTEGER PRIMARY KEY,
        business_id INTEGER NOT NULL,
        invoice_id INTEGER NOT NULL,
        product_id INTEGER,
        description TEXT NOT NULL,
        quantity REAL NOT NULL,
        unit_price REAL NOT NULL,
        unit_cost REAL NOT NULL DEFAULT 0,
        line_total REAL NOT NULL,
        FOREIGN KEY (business_id) REFERENCES businesses(id),
        FOREIGN KEY (invoice_id) REFERENCES invoices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY,
        business_id INTEGER NOT NULL,
        invoice_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        payment_date TEXT NOT NULL,
        method TEXT DEFAULT 'Cash',
        reference TEXT DEFAULT '',
        created_by INTEGER,
        FOREIGN KEY (business_id) REFERENCES businesses(id),
        FOREIGN KEY (invoice_id) REFERENCES invoices(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY,
        business_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        description TEXT DEFAULT '',
        amount REAL NOT NULL,
        expense_date TEXT NOT NULL,
        method TEXT DEFAULT 'Cash',
        created_by INTEGER,
        FOREIGN KEY (business_id) REFERENCES businesses(id)
    )
    """
]

def init_db():
    with engine.begin() as connection:
        for statement in SCHEMA:
            connection.execute(text(statement))

def execute(sql, params=None):
    with engine.begin() as connection:
        result = connection.execute(text(sql), params or {})
        return result.lastrowid

def query(sql, params=None):
    with engine.connect() as connection:
        result = connection.execute(text(sql), params or {})
        return [dict(row._mapping) for row in result.fetchall()]

def business_query(sql, business_id, params=None):
    """All business-data queries must include business_id."""
    values = dict(params or {})
    values["business_id"] = business_id
    return query(sql, values)

def business_execute(sql, business_id, params=None):
    """Write operations must be scoped to the current business."""
    values = dict(params or {})
    values["business_id"] = business_id
    return execute(sql, values)