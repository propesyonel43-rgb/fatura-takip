import os

DATABASE_URL = os.environ.get("DATABASE_URL")


class _PGCur:
    """Psycopg2 cursor wrapper that mimics sqlite3 cursor interface."""
    def __init__(self, raw_cur):
        self._c = raw_cur
        self.lastrowid = None

    def execute(self, q, p=()):
        q = q.replace("?", "%s")
        is_insert = q.strip().upper().startswith("INSERT")
        if is_insert and "RETURNING" not in q.upper():
            q = q.rstrip().rstrip(";") + " RETURNING id"
        self._c.execute(q, p)
        if is_insert:
            try:
                row = self._c.fetchone()
                if row:
                    self.lastrowid = list(dict(row).values())[0]
            except Exception:
                pass
        return self

    def fetchone(self):
        r = self._c.fetchone()
        return dict(r) if r else None

    def fetchall(self):
        rows = self._c.fetchall() or []
        return [dict(r) for r in rows]

    def __getitem__(self, k):
        return getattr(self._c, k)


class _PGConn:
    """Psycopg2 connection wrapper that mimics sqlite3 connection interface."""
    def __init__(self, raw):
        self._r = raw

    def cursor(self):
        import psycopg2.extras
        return _PGCur(self._r.cursor(cursor_factory=psycopg2.extras.RealDictCursor))

    def execute(self, q, p=()):
        cur = self.cursor()
        cur.execute(q, p)
        return cur

    def commit(self):
        self._r.commit()

    def rollback(self):
        self._r.rollback()

    def close(self):
        self._r.close()

    def executescript(self, sql):
        """Execute multiple statements separated by semicolons."""
        cur = self._r.cursor()
        for stmt in sql.split(";"):
            s = stmt.strip()
            if s:
                cur.execute(s)
        self._r.commit()


def get_db_connection():
    if DATABASE_URL:
        import psycopg2
        raw = psycopg2.connect(DATABASE_URL)
        return _PGConn(raw)
    else:
        import sqlite3
        conn = sqlite3.connect("database.db")
        conn.row_factory = sqlite3.Row
        return conn


# --- Schema ---
_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    phone_number TEXT,
    whatsapp_apikey TEXT DEFAULT ''
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
    is_autopay INTEGER DEFAULT 0,
    subscriber_no TEXT DEFAULT '',
    autopay_card_name TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS notification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id INTEGER NOT NULL,
    log_date TEXT NOT NULL,
    time_slot INTEGER NOT NULL,
    UNIQUE(bill_id, log_date, time_slot)
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
CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    owner TEXT NOT NULL,
    type TEXT NOT NULL,
    due_day INTEGER,
    current_balance REAL DEFAULT 0,
    active INTEGER DEFAULT 1,
    total_limit REAL DEFAULT 0,
    statement_day INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS card_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    transaction_date TEXT NOT NULL,
    note TEXT,
    FOREIGN KEY (card_id) REFERENCES cards (id)
);
CREATE TABLE IF NOT EXISTS card_notification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL,
    log_date TEXT NOT NULL,
    UNIQUE(card_id, log_date)
);
CREATE TABLE IF NOT EXISTS debt_collections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount REAL NOT NULL,
    collection_date TEXT NOT NULL,
    note TEXT
);
"""

_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    phone_number TEXT,
    whatsapp_apikey TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS bills (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    owner TEXT NOT NULL,
    amount REAL NOT NULL,
    due_day INTEGER NOT NULL,
    last_payment_day INTEGER NOT NULL,
    is_recurring INTEGER DEFAULT 1,
    category TEXT NOT NULL,
    active INTEGER DEFAULT 1,
    notes TEXT,
    is_autopay INTEGER DEFAULT 0,
    subscriber_no TEXT DEFAULT '',
    autopay_card_name TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS notification_log (
    id SERIAL PRIMARY KEY,
    bill_id INTEGER NOT NULL,
    log_date TEXT NOT NULL,
    time_slot INTEGER NOT NULL,
    UNIQUE(bill_id, log_date, time_slot)
);
CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    bill_id INTEGER NOT NULL,
    paid_by_user_id INTEGER NOT NULL,
    paid_for_owner TEXT NOT NULL,
    amount REAL NOT NULL,
    card_used TEXT NOT NULL,
    payment_date TEXT NOT NULL,
    is_on_behalf INTEGER DEFAULT 0,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS debts (
    id SERIAL PRIMARY KEY,
    payment_id INTEGER NOT NULL,
    debtor_user_id INTEGER NOT NULL,
    creditor_user_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    is_paid INTEGER DEFAULT 0,
    paid_date TEXT
);
CREATE TABLE IF NOT EXISTS monthly_cycles (
    id SERIAL PRIMARY KEY,
    bill_id INTEGER NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    status TEXT NOT NULL,
    payment_id INTEGER
);
CREATE TABLE IF NOT EXISTS cards (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    owner TEXT NOT NULL,
    type TEXT NOT NULL,
    due_day INTEGER,
    current_balance REAL DEFAULT 0,
    active INTEGER DEFAULT 1,
    total_limit REAL DEFAULT 0,
    statement_day INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS card_transactions (
    id SERIAL PRIMARY KEY,
    card_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    transaction_date TEXT NOT NULL,
    note TEXT
);
CREATE TABLE IF NOT EXISTS card_notification_log (
    id SERIAL PRIMARY KEY,
    card_id INTEGER NOT NULL,
    log_date TEXT NOT NULL,
    UNIQUE(card_id, log_date)
);
CREATE TABLE IF NOT EXISTS debt_collections (
    id SERIAL PRIMARY KEY,
    amount REAL NOT NULL,
    collection_date TEXT NOT NULL,
    note TEXT
);
"""


def init_db():
    conn = get_db_connection()
    if DATABASE_URL:
        conn.executescript(_PG_SCHEMA)
    else:
        conn.executescript(_SQLITE_SCHEMA)
    # Migrations for existing databases
    try:
        conn.execute("ALTER TABLE bills ADD COLUMN subscriber_no TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        try: conn.rollback()
        except: pass
    try:
        conn.execute("ALTER TABLE users ADD COLUMN whatsapp_apikey TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        try: conn.rollback()
        except: pass
    
    # Metin'in giriş yapabilmesi için gizli hesabı açığa çıkart ve şifre belirle (sadece 1 kez çalışır)
    try:
        from werkzeug.security import generate_password_hash
        conn.execute("UPDATE users SET username = 'metin', password_hash = ? WHERE display_name = 'Metin' AND username = 'metin_hidden'", 
                     (generate_password_hash('1964', method='pbkdf2:sha256'),))
        conn.commit()
    except Exception:
        try: conn.rollback()
        except: pass

    try:
        if DATABASE_URL:
            conn.execute("CREATE TABLE IF NOT EXISTS notification_log (id SERIAL PRIMARY KEY, bill_id INTEGER NOT NULL, log_date TEXT NOT NULL, time_slot INTEGER NOT NULL, UNIQUE(bill_id, log_date, time_slot))")
            conn.execute("ALTER TABLE debts ALTER COLUMN payment_id DROP NOT NULL")
        else:
            conn.execute("CREATE TABLE IF NOT EXISTS notification_log (id INTEGER PRIMARY KEY AUTOINCREMENT, bill_id INTEGER NOT NULL, log_date TEXT NOT NULL, time_slot INTEGER NOT NULL, UNIQUE(bill_id, log_date, time_slot))")
        conn.commit()
    except Exception:
        try: conn.rollback()
        except: pass

    # New card tables migration
    try:
        if DATABASE_URL:
            conn.execute("CREATE TABLE IF NOT EXISTS cards (id SERIAL PRIMARY KEY, name TEXT NOT NULL, owner TEXT NOT NULL, type TEXT NOT NULL, due_day INTEGER, current_balance REAL DEFAULT 0, active INTEGER DEFAULT 1)")
            conn.execute("CREATE TABLE IF NOT EXISTS card_transactions (id SERIAL PRIMARY KEY, card_id INTEGER NOT NULL, amount REAL NOT NULL, transaction_date TEXT NOT NULL, note TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS card_notification_log (id SERIAL PRIMARY KEY, card_id INTEGER NOT NULL, log_date TEXT NOT NULL, UNIQUE(card_id, log_date))")
        else:
            conn.execute("CREATE TABLE IF NOT EXISTS cards (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, owner TEXT NOT NULL, type TEXT NOT NULL, due_day INTEGER, current_balance REAL DEFAULT 0, active INTEGER DEFAULT 1)")
            conn.execute("CREATE TABLE IF NOT EXISTS card_transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, card_id INTEGER NOT NULL, amount REAL NOT NULL, transaction_date TEXT NOT NULL, note TEXT, FOREIGN KEY (card_id) REFERENCES cards (id))")
            conn.execute("CREATE TABLE IF NOT EXISTS card_notification_log (id INTEGER PRIMARY KEY AUTOINCREMENT, card_id INTEGER NOT NULL, log_date TEXT NOT NULL, UNIQUE(card_id, log_date))")
        conn.commit()
    except Exception:
        try: conn.rollback()
        except: pass

    # Migration: New card columns (total_limit, statement_day)
    try:
        conn.execute("ALTER TABLE cards ADD COLUMN total_limit REAL DEFAULT 0")
        conn.commit()
    except Exception:
        try: conn.rollback()
        except: pass
    try:
        conn.execute("ALTER TABLE cards ADD COLUMN statement_day INTEGER DEFAULT 1")
        conn.commit()
    except Exception:
        try: conn.rollback()
        except: pass

    # Migration: bills table (autopay_card_name)
    try:
        conn.execute("ALTER TABLE bills ADD COLUMN autopay_card_name TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        try: conn.rollback()
        except: pass

    # Migration: debt_collections table
    try:
        if DATABASE_URL:
            conn.execute("CREATE TABLE IF NOT EXISTS debt_collections (id SERIAL PRIMARY KEY, amount REAL NOT NULL, collection_date TEXT NOT NULL, note TEXT)")
        else:
            conn.execute("CREATE TABLE IF NOT EXISTS debt_collections (id INTEGER PRIMARY KEY AUTOINCREMENT, amount REAL NOT NULL, collection_date TEXT NOT NULL, note TEXT)")
        conn.commit()
    except Exception:
        try: conn.rollback()
        except: pass

    # Migration: payments table (card_id) - hangi kartla odendigini net olarak tutmak icin
    try:
        conn.execute("ALTER TABLE payments ADD COLUMN card_id INTEGER")
        conn.commit()
    except Exception:
        try: conn.rollback()
        except: pass

    conn.close()


def get_all_users():
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_config(key, default=""):
    conn = get_db_connection()
    row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    conn.close()
    if row:
        return dict(row)["value"] if hasattr(row, "keys") else row["value"]
    return default


def set_config(key, value):
    conn = get_db_connection()
    if DATABASE_URL:
        conn.execute(
            "INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",
            (key, value)
        )
    else:
        conn.execute(
            "INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value)
        )
    conn.commit()
    conn.close()
