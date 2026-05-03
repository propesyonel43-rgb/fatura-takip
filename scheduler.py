from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import notifier
import database

def check_bills_and_notify():
    today = datetime.now()
    conn = database.get_db_connection()
    bills = conn.execute("SELECT * FROM bills WHERE active = 1").fetchall()
    
    for b in bills:
        cycle = conn.execute("SELECT status FROM monthly_cycles WHERE bill_id = ? AND year = ? AND month = ?", 
                             (b['id'], today.year, today.month)).fetchone()
        
        if cycle and cycle["status"] == "odendi":
            continue
            
        message = ""
        is_last_day = (b['last_payment_day'] == today.day)
        is_due_day = (b['due_day'] == today.day)
        
        if is_last_day or is_due_day:
            if b['is_autopay']:
                if is_last_day:
                    message = f"ℹ️ BUGUN OTO-ODEME SON GUN: {b['name']} ({b['amount']}TL) hesaptan cekilecek, kontrol et."
                else:
                    message = f"ℹ️ YAKLASAN OTO-ODEME: {b['name']} ({b['amount']}TL) hesaptan cekilecek."
            else:
                if is_last_day:
                    message = f"!!! DIKKAT: BUGUN SON GUN !!!\n{b['name']} faturasinin ({b['amount']}TL) son odeme gunu. Lutfen odeyin."
                else:
                    message = f"🔔 HATIRLATMA: {b['name']} faturasinin ({b['amount']}TL) odeme gunu geldi."
                    
            notifier.notify_all(message)
            
    conn.close()

def start_scheduler():
    scheduler = BackgroundScheduler(daemon=True)
    # Render vb. uyuyan sunucularda gunde 3 kez tetikleme (sunucu uyaniksa calisir)
    scheduler.add_job(check_bills_and_notify, 'cron', hour=10, minute=0)
    scheduler.add_job(check_bills_and_notify, 'cron', hour=15, minute=0)
    scheduler.add_job(check_bills_and_notify, 'cron', hour=21, minute=0)
    scheduler.start()
