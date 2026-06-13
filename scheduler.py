from datetime import datetime, timezone, timedelta
import notifier
import database

# Türkiye saati (UTC+3) — harici paket gerekmez
TURKEY_TZ = timezone(timedelta(hours=3))

NOTIFICATION_SLOTS = [10, 21]  # Saat 10:00 ve 21:00 TR saatiyle


def check_bills_and_notify():
    now = datetime.now(TURKEY_TZ)
    current_slot = now.hour  # Hangi saatte çağrıldıysa o slot
    
    # Sadece belirlenen saatlerde (10, 21) çalış.
    if current_slot not in NOTIFICATION_SLOTS:
        return
        
    today_str = now.strftime('%Y-%m-%d')
    conn = database.get_db_connection()
    bills = conn.execute("SELECT * FROM bills WHERE active = 1").fetchall()

    alerts = []

    for b in bills:
        bill = dict(b) if not isinstance(b, dict) else b

        # Bu ay ödendi mi?
        cycle = conn.execute(
            "SELECT status FROM monthly_cycles WHERE bill_id = ? AND year = ? AND month = ?",
            (bill['id'], now.year, now.month)
        ).fetchone()

        if cycle and (dict(cycle) if not isinstance(cycle, dict) else cycle).get('status') == 'odendi':
            continue

        # Tek seferlik fatura, gecmiste herhangi bir ayda odenmisse bir daha hatirlatma
        if not bill['is_recurring']:
            paid_ever = conn.execute(
                "SELECT id FROM monthly_cycles WHERE bill_id = ? AND status = 'odendi'",
                (bill['id'],)
            ).fetchone()
            if paid_ever:
                continue

        is_last_day = (bill['last_payment_day'] == now.day)
        is_due_day = (bill['due_day'] == now.day)
        days_left = bill['due_day'] - now.day
        is_approaching = (0 < days_left <= 3)
        
        is_overdue = (now.day > bill['last_payment_day'])
        days_overdue = now.day - bill['last_payment_day'] if is_overdue else 0

        if not (is_last_day or is_due_day or is_approaching or is_overdue):
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
        msg = ""
        if bill['is_autopay']:
            if is_overdue:
                msg = f"🔴 GECİKMİŞ OTO-ÖDEME: {bill['name']}{abone} ({format_para(bill['amount'])} TL) {days_overdue} gün gecikmede! Hesabı kontrol edin."
            elif is_last_day:
                msg = f"ℹ️ BUGÜN OTO-ÖDEME SON GÜN: {bill['name']}{abone} ({format_para(bill['amount'])} TL) hesaptan çekilecek."
            else:
                msg = f"ℹ️ YAKLAŞAN OTO-ÖDEME: {bill['name']}{abone} ({format_para(bill['amount'])} TL) - {days_left} gün kaldı."
        else:
            if is_overdue:
                msg = f"🔴 DİKKAT GECİKMİŞ ÖDEME: {bill['name']}{abone} faturası ({format_para(bill['amount'])} TL) tam {days_overdue} gün gecikti! Lütfen hemen ödeyin."
            elif is_last_day:
                msg = f"⚠️ BUGÜN SON GÜN! {bill['name']}{abone} faturası ({format_para(bill['amount'])} TL) — LÜTFEN BUGÜN ÖDEYİN!"
            elif is_due_day:
                msg = f"🔔 ÖDEME GÜNÜ: {bill['name']}{abone} faturası ({format_para(bill['amount'])} TL) ödeme günü geldi."
            else:
                msg = f"🔔 {days_left} GÜN KALDI: {bill['name']}{abone} faturası ({format_para(bill['amount'])} TL)"

        alerts.append(msg)

        # Log: Defalarca mesaj gitmesin
        try:
            conn.execute(
                "INSERT INTO notification_log (bill_id, log_date, time_slot) VALUES (?, ?, ?)",
                (bill['id'], today_str, current_slot)
            )
            conn.commit()
        except Exception as e:
            print(f"[Bildirim Log Hatası]: {e}")

    # KARTLARI KONTROL ET
    try:
        card_alerts = get_card_notifications(conn, now, today_str)
        alerts.extend(card_alerts)
    except Exception as e:
        print(f"[Kart Bildirim Hata]: {e}")
        
    conn.close()

    # Eğer toplu bir mesaj varsa gönder
    if alerts:
        final_msg = "🔔 *Faturalar & Kartlar - Güncel Durum*\n\n" + "\n\n".join(alerts)
        notifier.notify_all(final_msg)

    # AY SONU ÖZETİ: Her ayın son günü saat 21:00'de genel rapor atar
    import calendar
    if now.hour == 21 and now.day == calendar.monthrange(now.year, now.month)[1]:
        send_monthly_summary(now.year, now.month)

    print(f"[Cron] {now.strftime('%d.%m.%Y %H:%M')} TR saatiyle kontrol tamamlandı.")


def get_card_notifications(conn, now, today_str):
    current_slot = now.hour
    # Sadece sabah 10 slotunda kart kontrolü yapalım
    if current_slot != 10:
        return []

    alerts = []
    cards = conn.execute("SELECT * FROM cards WHERE active = 1").fetchall()

    for c in cards:
        card = dict(c) if not isinstance(c, dict) else c
        card_id = card['id']
        balance = card['current_balance']
        
        # Sadece eksi bakiye (borç) varken hatırlat
        if balance >= 0:
            continue
            
        # Dedup: Bu kart için bugün mesaj listesine eklendi/gitti mi?
        existing_log = conn.execute(
            "SELECT id FROM card_notification_log WHERE card_id = ? AND log_date = ?",
            (card_id, today_str)
        ).fetchone()
        
        if existing_log:
            continue
        
        notify_msg = None
        
        # 1. Son Ödemeye 3 Gün Kala (Her sabah)
        if card['type'] == 'Kredi Kartı' and card.get('due_day'):
            days_left = card['due_day'] - now.day
            # Ay dönümünü basitçe hesapla (örneğin due_day=5, now.day=28 ise days_left negatiftir)
            # Eğer günler uyuşmuyorsa bir sonraki aya kalmıştır, basitleştirmek adına:
            if days_left < 0:
                import calendar
                last_day = calendar.monthrange(now.year, now.month)[1]
                days_left = (last_day - now.day) + card['due_day']

            if 0 <= days_left <= 3:
                if days_left == 0:
                    notify_msg = f"💳 Abi *{card['name']}* kartının BUGÜN son ödeme günü! (Bakiye: {format_para(balance)} TL)"
                else:
                    notify_msg = f"💳 Abi *{card['name']}* kartının son ödemesine {days_left} gün kaldı. (Bakiye: {format_para(balance)} TL)"
        
        # 2. Periyodik Hatırlatma (Eksi bakiye varsa ve 10 gündür mesaj gitmediyse)
        if not notify_msg:
            # En son ne zaman mesaj gitmiş?
            last_log = conn.execute(
                "SELECT log_date FROM card_notification_log WHERE card_id = ? ORDER BY log_date DESC LIMIT 1",
                (card_id,)
            ).fetchone()
            
            should_notify_periodic = False
            if not last_log:
                should_notify_periodic = True
            else:
                last_date_str = last_log['log_date'] if isinstance(last_log, dict) else last_log[0]
                last_date = datetime.strptime(last_date_str, '%Y-%m-%d').replace(tzinfo=TURKEY_TZ)
                if (now - last_date).days >= 10:
                    should_notify_periodic = True
            
            if should_notify_periodic:
                notify_msg = f"⚠️ Hatırlatma: *{card['name']}* kartında {format_para(balance)} TL borç/eksi görünüyor."

        if notify_msg:
            alerts.append(notify_msg)
            # Logla (Bugün mesaj listesine eklendi)
            try:
                conn.execute(
                    "INSERT INTO card_notification_log (card_id, log_date) VALUES (?, ?)",
                    (card_id, today_str)
                )
                conn.commit()
            except Exception as e:
                print(f"[Kart Log Hatası]: {e}")

    return alerts


def format_para(value):
    """Rakamı 10.000,00 TL formatına sokar."""
    try:
        return "{:,.2f}".format(float(value)).replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return value

def send_monthly_summary(year, month):
    """Ay sonu genel durumunu WhatsApp'tan raporlar."""
    conn = database.get_db_connection()
    month_names = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
    
    # Bu ay yapılan ödemeler
    start_date = f"{year}-{month:02d}-01"
    end_date   = f"{year}-{month:02d}-31"
    
    payments = conn.execute("""
        SELECT p.*, b.name as bill_name, mc.year as b_year, mc.month as b_month
        FROM payments p
        JOIN bills b ON p.bill_id = b.id
        LEFT JOIN monthly_cycles mc ON p.id = mc.payment_id
        WHERE p.payment_date >= ? AND p.payment_date <= ?
    """, (start_date, end_date)).fetchall()

    total = sum(p['amount'] for p in payments)

    # Bekleyenler
    bills = conn.execute("SELECT * FROM bills WHERE active = 1").fetchall()
    bekleyen = []
    for b in bills:
        cycle = conn.execute("SELECT status FROM monthly_cycles WHERE bill_id=? AND year=? AND month=?", (b['id'], year, month)).fetchone()
        if not cycle or cycle['status'] != 'odendi':
            bekleyen.append(f"• {b['name']} ({format_para(b['amount'])} ₺)")

    # Kim ne ödedi (bu ay)
    kim_ne_odedi = conn.execute("""
        SELECT u.display_name, SUM(p.amount) as total
        FROM payments p
        JOIN users u ON p.paid_by_user_id = u.id
        WHERE p.payment_date >= ? AND p.payment_date <= ?
        GROUP BY u.display_name
    """, (start_date, end_date)).fetchall()

    # Kart bakiyeleri
    cards = conn.execute("SELECT * FROM cards WHERE active = 1 ORDER BY owner, name").fetchall()

    # Metin'in Fahri'ye güncel net borcu
    fahri = conn.execute("SELECT id FROM users WHERE display_name = 'Fahri'").fetchone()
    metin = conn.execute("SELECT id FROM users WHERE display_name = 'Metin'").fetchone()
    metin_debt = 0
    if fahri and metin:
        debt_row = conn.execute("SELECT SUM(amount) as t FROM debts WHERE debtor_user_id = ? AND creditor_user_id = ? AND is_paid = 0", (metin['id'], fahri['id'])).fetchone()
        metin_debt = debt_row['t'] or 0

    msg = f"🏁 *{month_names[month]} {year} AY SONU ÖZETİ*\n"
    msg += "-----------------------------------\n"
    msg += f"💰 *Toplam Harcanan:* {format_para(total)} ₺\n"

    if kim_ne_odedi:
        msg += "\n*👤 Kim Ne Ödedi:*\n"
        for k in kim_ne_odedi:
            msg += f"• {k['display_name']}: {format_para(k['total'] or 0)} ₺\n"

    if payments:
        msg += "\n*✅ Ödenenler:*\n"
        for p in payments:
            donem = f"{p['b_month']}/{p['b_year']}" if p.get('b_month') else "Manuel"
            msg += f"• {p['bill_name']} ({donem}): {format_para(p['amount'])} ₺\n"

    if bekleyen:
        msg += "\n*⏳ Ödenmeyenler (Kalan):*\n"
        msg += "\n".join(bekleyen) + "\n"
    else:
        msg += "\n*✅ Harika! Bu ay tüm faturalar kapatıldı.*\n"

    if cards:
        msg += "\n*💳 Kart Bakiyeleri:*\n"
        for c in cards:
            msg += f"• {c['name']} ({c['owner']}): {format_para(c['current_balance'])} ₺\n"

    msg += f"\n*🤝 Metin'in Fahri'ye Net Borcu:* {format_para(metin_debt)} ₺"

    notifier.notify_all(msg)
    conn.close()


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
    print("[Scheduler] Dahili zamanlayıcı başlatıldı (10:00 ve 21:00).")
