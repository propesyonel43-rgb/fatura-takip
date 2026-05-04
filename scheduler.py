from datetime import datetime, timezone, timedelta
import notifier
import database

# Türkiye saati (UTC+3) — harici paket gerekmez
TURKEY_TZ = timezone(timedelta(hours=3))

NOTIFICATION_SLOTS = [10, 15, 21]  # Saat 10:00, 15:00, 21:00 TR saatiyle


def check_bills_and_notify():
    now = datetime.now(TURKEY_TZ)
    today_str = now.strftime('%Y-%m-%d')
    current_slot = now.hour  # Hangi saatte çağrıldıysa o slot

    conn = database.get_db_connection()
    bills = conn.execute("SELECT * FROM bills WHERE active = 1").fetchall()

    for b in bills:
        bill = dict(b) if not isinstance(b, dict) else b

        # Bu ay ödendi mi?
        cycle = conn.execute(
            "SELECT status FROM monthly_cycles WHERE bill_id = ? AND year = ? AND month = ?",
            (bill['id'], now.year, now.month)
        ).fetchone()

        if cycle and (dict(cycle) if not isinstance(cycle, dict) else cycle).get('status') == 'odendi':
            continue

        is_last_day = (bill['last_payment_day'] == now.day)
        is_due_day = (bill['due_day'] == now.day)
        days_left = bill['due_day'] - now.day
        is_approaching = (0 < days_left <= 3)

        if not (is_last_day or is_due_day or is_approaching):
            continue

        # Dedup: Bu bill için bugün bu slot'ta mesaj gitti mi?
        existing = conn.execute(
            "SELECT id FROM notification_log WHERE bill_id = ? AND log_date = ? AND time_slot = ?",
            (bill['id'], today_str, current_slot)
        ).fetchone()

        if existing:
            continue

        # Mesaj oluştur
        abone = f" (Abone: {bill['subscriber_no']})" if bill.get('subscriber_no') else ""
        if bill['is_autopay']:
            if is_last_day:
                msg = f"ℹ️ BUGÜN OTO-ÖDEME SON GÜN: {bill['name']}{abone} ({bill['amount']}TL) hesaptan çekilecek."
            else:
                msg = f"ℹ️ YAKLAŞAN OTO-ÖDEME: {bill['name']}{abone} ({bill['amount']}TL) - {days_left} gün kaldı."
        else:
            if is_last_day:
                msg = f"⚠️ BUGÜN SON GÜN! {bill['name']}{abone} faturası ({bill['amount']}TL) — LÜTFEN BUGÜN ÖDEYİN!"
            elif is_due_day:
                msg = f"🔔 ÖDEME GÜNÜ: {bill['name']}{abone} faturası ({bill['amount']}TL) ödeme günü geldi."
            else:
                msg = f"🔔 {days_left} GÜN KALDI: {bill['name']}{abone} faturası ({bill['amount']}TL)"

        notifier.notify_all(msg)

        # Log: Defalarca mesaj gitmesin
        try:
            conn.execute(
                "INSERT INTO notification_log (bill_id, log_date, time_slot) VALUES (?, ?, ?)",
                (bill['id'], today_str, current_slot)
            )
            conn.commit()
        except Exception as e:
            print(f"[Bildirim Log Hatası]: {e}")

    conn.close()
    print(f"[Cron] {now.strftime('%d.%m.%Y %H:%M')} TR saatiyle kontrol tamamlandı.")


def start_scheduler():
    """Sadece lokal geliştirmede kullan; Render'da dış cron yeter."""
    import os
    if os.environ.get("DATABASE_URL"):
        print("[Scheduler] Render ortamı: dahili scheduler devre dışı (dış cron kullanılıyor).")
        return

    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler(daemon=True)
    # Lokal test için Türkiye saatleri (yerel makine TR saatindeyse uygundur)
    for h in NOTIFICATION_SLOTS:
        scheduler.add_job(check_bills_and_notify, 'cron', hour=h, minute=0)
    scheduler.start()
    print("[Scheduler] Dahili zamanlayıcı başlatıldı (10:00, 15:00, 21:00).")
