"""Eski Render PostgreSQL veritabanindaki tum verileri yeni veritabanina (Neon) tasir.

Kullanim:
    venv/bin/python migrate.py "<ESKI_DATABASE_URL>" "<YENI_DATABASE_URL>"
"""
import sys
import psycopg2
import psycopg2.extras

from database import _PG_SCHEMA

# Foreign key sirasina gore: once referans verilen tablolar
TABLES = [
    "users",
    "config",
    "categories",
    "bills",
    "payments",
    "debts",
    "monthly_cycles",
    "notification_log",
    "cards",
    "card_transactions",
    "card_notification_log",
    "debt_collections",
]


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    src_url, dst_url = sys.argv[1], sys.argv[2]

    src = psycopg2.connect(src_url)
    dst = psycopg2.connect(dst_url)
    src_cur = src.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    dst_cur = dst.cursor()

    print("Yeni veritabaninda tablolar olusturuluyor...")
    for stmt in _PG_SCHEMA.split(";"):
        if stmt.strip():
            dst_cur.execute(stmt)
    dst.commit()

    for table in TABLES:
        try:
            src_cur.execute(f"SELECT * FROM {table}")
        except psycopg2.Error:
            src.rollback()
            print(f"  {table}: eski veritabaninda yok, atlandi")
            continue
        rows = src_cur.fetchall()
        if not rows:
            print(f"  {table}: 0 kayit")
            continue
        cols = list(rows[0].keys())
        col_list = ", ".join(cols)
        placeholders = ", ".join(["%s"] * len(cols))
        for row in rows:
            dst_cur.execute(
                f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING",
                [row[c] for c in cols],
            )
        dst.commit()
        # SERIAL sayaclarini en son id'ye ayarla, yoksa yeni kayitlar eski id'lerle cakisir
        if "id" in cols:
            dst_cur.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT MAX(id) FROM {table}))"
            )
            dst.commit()
        print(f"  {table}: {len(rows)} kayit tasindi")

    print("\nKontrol — yeni veritabanindaki kayit sayilari:")
    for table in TABLES:
        dst_cur.execute(f"SELECT COUNT(*) FROM {table}")
        print(f"  {table}: {dst_cur.fetchone()[0]}")

    src.close()
    dst.close()
    print("\nTasima tamamlandi!")


if __name__ == "__main__":
    main()
