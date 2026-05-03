import sqlite3

DATABASE = 'database.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        display_name TEXT NOT NULL,
        phone_number TEXT
    );

    CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY,
        value TEXT
    );

    CREATE TABLE IF NOT EXISTS bills (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        owner TEXT NOT NULL,
        amount REAL NOT NULL,
        due_day INTEGER NOT NULL,
        last_payment_day INTEGER NOT NULL,
        is_recurring INTEGER DEFAULT 1,
        category TEXT NOT NULL,
        active INTEGER DEFAULT 1,
        notes TEXT,
        is_autopay INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    );

    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bill_id INTEGER NOT NULL,
        paid_by_user_id INTEGER NOT NULL,
        paid_for_owner TEXT NOT NULL,
        amount REAL NOT NULL,
        card_used TEXT NOT NULL,
        payment_date TEXT NOT NULL,
        is_on_behalf INTEGER DEFAULT 0,
        notes TEXT,
        FOREIGN KEY (bill_id) REFERENCES bills (id),
        FOREIGN KEY (paid_by_user_id) REFERENCES users (id)
    );

    CREATE TABLE IF NOT EXISTS debts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        payment_id INTEGER NOT NULL,
        debtor_user_id INTEGER NOT NULL,
        creditor_user_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        is_paid INTEGER DEFAULT 0,
        paid_date TEXT,
        FOREIGN KEY (payment_id) REFERENCES payments (id),
        FOREIGN KEY (debtor_user_id) REFERENCES users (id),
        FOREIGN KEY (creditor_user_id) REFERENCES users (id)
    );

    CREATE TABLE IF NOT EXISTS monthly_cycles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bill_id INTEGER NOT NULL,
        year INTEGER NOT NULL,
        month INTEGER NOT NULL,
        status TEXT NOT NULL,
        payment_id INTEGER,
        FOREIGN KEY (bill_id) REFERENCES bills (id),
        FOREIGN KEY (payment_id) REFERENCES payments (id)
    );
    """)
    conn.commit()
    conn.close()

def get_all_users():
    conn = get_db_connection()
    users = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    return [dict(u) for u in users]

def get_config(key, default=""):
    conn = get_db_connection()
    row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default

def set_config(key, value):
    conn = get_db_connection()
    conn.execute("INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit()
    conn.close()
