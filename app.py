import os

# Render'ın PostgreSQL URL'si "postgres://" ile başlar ama psycopg2 "postgresql://" ister
_db_url = os.environ.get("DATABASE_URL", "")
if _db_url.startswith("postgres://"):
    os.environ["DATABASE_URL"] = _db_url.replace("postgres://", "postgresql://", 1)

from flask import Flask, render_template_string, request, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import calendar
from jinja2 import DictLoader

import database
import notifier
from scheduler import start_scheduler, check_bills_and_notify

app = Flask(__name__)
app.secret_key = 'super-secret-key-change-this'

# Initialize DB
database.init_db()

# Insert default categories if none exist
_conn = database.get_db_connection()
_row = _conn.execute("SELECT COUNT(*) FROM categories").fetchone()
_cnt = list(_row.values())[0] if isinstance(_row, dict) else _row[0]
if _cnt == 0:
    for _cat in ['Elektrik', 'Su', 'Doğalgaz', 'İnternet', 'Telefon', 'Kira', 'Diğer']:
        try:
            _conn.execute("INSERT INTO categories (name) VALUES (?)", (_cat,))
        except Exception:
            pass
    _conn.commit()
_conn.close()

# Initialize Scheduler
start_scheduler()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, user_data):
        self.id = user_data["id"]
        self.username = user_data["username"]
        self.display_name = user_data["display_name"]
        self.phone_number = user_data.get("phone_number")
        self.whatsapp_apikey = user_data.get("whatsapp_apikey", "")

@login_manager.user_loader
def load_user(user_id):
    conn = database.get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if user:
        return User(dict(user))
    return None

BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Fatura Takip</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        :root {
            --primary: #6366f1;
            --primary-light: #818cf8;
            --primary-dark: #4f46e5;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --bg: #f1f5f9;
            --surface: #ffffff;
            --text: #1e293b;
            --text-muted: #64748b;
            --border: #e2e8f0;
        }
        * { box-sizing: border-box; }
        body { font-family: 'Inter', sans-serif; padding-bottom: 80px; background-color: var(--bg); color: var(--text); }
        .container { max-width: 540px; }
        /* --- Navbar --- */
        .navbar-bottom {
            position: fixed; bottom: 0; width: 100%; z-index: 1030;
            background: rgba(255,255,255,0.95);
            backdrop-filter: blur(12px);
            box-shadow: 0 -1px 0 var(--border);
            display: flex; justify-content: space-around;
            padding: 6px 0 10px;
        }
        .nav-link {
            display: flex; flex-direction: column; align-items: center;
            font-size: 0.7rem; color: var(--text-muted); text-decoration: none;
            padding: 4px 12px; border-radius: 12px;
            transition: all 0.2s ease;
        }
        .nav-link.active { color: var(--primary); font-weight: 600; }
        .nav-link:hover { color: var(--primary); background: #eef2ff; }
        .nav-icon { font-size: 1.3rem; margin-bottom: 2px; }
        /* --- Cards --- */
        .card {
            border-radius: 16px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 4px 12px rgba(0,0,0,0.04);
            border: 1px solid var(--border);
            background: var(--surface);
            margin-bottom: 14px;
            transition: box-shadow 0.2s;
        }
        .card:hover { box-shadow: 0 4px 20px rgba(0,0,0,0.1); }
        /* --- Page Header --- */
        .page-title { font-size: 1.4rem; font-weight: 700; color: var(--text); }
        /* --- Hero Card (Debt) --- */
        .hero-card {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white; border-radius: 20px; padding: 24px;
            box-shadow: 0 8px 24px rgba(99,102,241,0.35);
            border: none; margin-bottom: 20px;
        }
        .hero-card .label { font-size: 0.8rem; opacity: 0.8; font-weight: 500; letter-spacing: 0.05em; text-transform: uppercase; }
        .hero-card .amount { font-size: 2.8rem; font-weight: 700; line-height: 1.1; }
        /* --- Bill Chips --- */
        .bill-chip {
            border-radius: 14px; padding: 14px;
            display: flex; flex-direction: column; gap: 4px;
            font-size: 0.85rem; transition: transform 0.15s;
        }
        .bill-chip:hover { transform: translateY(-2px); }
        .chip-success { background: #ecfdf5; border: 1.5px solid #6ee7b7; color: #065f46; }
        .chip-warning { background: #fffbeb; border: 1.5px solid #fcd34d; color: #92400e; }
        .chip-danger { background: #fef2f2; border: 1.5px solid #fca5a5; color: #991b1b; }
        .chip-light { background: #f8fafc; border: 1.5px solid var(--border); color: var(--text); }
        /* --- Buttons --- */
        .btn-primary { background: var(--primary); border-color: var(--primary); }
        .btn-primary:hover { background: var(--primary-dark); border-color: var(--primary-dark); }
        .btn-success { background: var(--success); border-color: var(--success); }
        /* --- Sections --- */
        .section-title { font-size: 0.75rem; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 10px; }
        /* --- List Group --- */
        .list-group-item { border-color: var(--border); padding: 14px 16px; }
        .list-group-item:first-child { border-radius: 14px 14px 0 0; }
        .list-group-item:last-child { border-radius: 0 0 14px 14px; }
        .list-group-item:only-child { border-radius: 14px; }
        /* --- Form Controls --- */
        .form-control, .form-select {
            border: 1.5px solid var(--border); border-radius: 12px;
            font-size: 0.95rem; color: var(--text);
            transition: border-color 0.2s, box-shadow 0.2s;
        }
        .form-control:focus, .form-select:focus {
            border-color: var(--primary); box-shadow: 0 0 0 3px rgba(99,102,241,0.15);
        }
        /* --- Custom Radio/Btn --- */
        .btn-check-custom + .btn { border-radius: 12px; padding: 12px 8px; font-size: 0.95rem; font-weight: 500; border: 1.5px solid var(--border); color: var(--text-muted); }
        .btn-check-custom:checked + .btn { background: var(--primary); border-color: var(--primary); color: white; }
        /* --- Calendar --- */
        .calendar-table th, .calendar-table td { text-align: center; vertical-align: top; width: 14%; height: 76px; }
        .day-number { font-weight: 600; font-size: 0.85rem; color: var(--text-muted); }
        .cal-item { font-size: 0.7rem; border-radius: 6px; padding: 2px 3px; margin-top: 2px; font-weight: 500; }
        .cal-item.success { background: #d1fae5; color: #065f46; }
        .cal-item.warning { background: #fef3c7; color: #92400e; }
        .cal-item.danger { background: #fee2e2; color: #991b1b; }
        /* --- Login --- */
        .login-card { border-radius: 24px; padding: 32px; box-shadow: 0 20px 60px rgba(0,0,0,0.1); }
        /* --- Badge tweaks --- */
        .badge { font-weight: 500; }
    </style>
</head>
<body>
    <div class="container mt-4 mb-5 pb-4">
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
                {{ message }}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
              </div>
            {% endfor %}
          {% endif %}
        {% endwith %}
        
        {% block content %}{% endblock %}
    </div>

    {% if current_user.is_authenticated %}
    <nav class="navbar-bottom">
        <a href="{{ url_for('dashboard') }}" class="nav-link {% if request.endpoint == 'dashboard' %}active{% endif %}">
            <span class="nav-icon">🏠</span> Anasayfa
        </a>
        <a href="{{ url_for('faturalar') }}" class="nav-link {% if request.endpoint in ['faturalar', 'kategoriler'] %}active{% endif %}">
            <span class="nav-icon">📄</span> Faturalar
        </a>
        <a href="{{ url_for('odeme_kaydet') }}" class="nav-link {% if request.endpoint == 'odeme_kaydet' %}active{% endif %}">
            <span class="nav-icon">💳</span> Öde
        </a>
        <a href="{{ url_for('borclar') }}" class="nav-link {% if request.endpoint == 'borclar' %}active{% endif %}">
            <span class="nav-icon">🤝</span> Borçlar
        </a>
        <a href="{{ url_for('kartlar') }}" class="nav-link {% if request.endpoint in ['kartlar', 'kart_detay'] %}active{% endif %}">
            <span class="nav-icon">💳</span> Kartlar
        </a>
        <a href="{{ url_for('raporlar') }}" class="nav-link {% if request.endpoint == 'raporlar' %}active{% endif %}">
            <span class="nav-icon">📊</span> Rapor
        </a>
    </nav>
    {% endif %}

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    {% block scripts %}{% endblock %}
</body>
</html>
"""

def format_para(value):
    """Rakamı 10.000,00 TL formatına sokar."""
    try:
        return "{:,.2f}".format(float(value)).replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return value

app.jinja_env.filters['para'] = format_para
app.jinja_env.loader = DictLoader({'base.html': BASE_TEMPLATE})

@app.before_request
def check_setup():
    if request.endpoint not in ['setup', 'static'] and not request.endpoint.startswith('__'):
        conn = database.get_db_connection()
        row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
        user_count = list(row.values())[0] if isinstance(row, dict) else row[0]
        conn.close()
        if user_count == 0:
            return redirect(url_for('setup'))

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    conn = database.get_db_connection()
    row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
    user_count = list(row.values())[0] if isinstance(row, dict) else row[0]
    if user_count > 0:
        conn.close()
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        f_user = request.form.get('fahri_username')
        f_pass = request.form.get('fahri_password')
        f_phone = request.form.get('fahri_phone')
        
        m_user = request.form.get('metin_username', 'metin')
        m_pass = request.form.get('metin_password', '1964')
        m_phone = request.form.get('metin_phone')
        
        conn.execute("INSERT INTO users (username, password_hash, display_name, phone_number) VALUES (?, ?, ?, ?)",
                     (f_user, generate_password_hash(f_pass, method='pbkdf2:sha256'), "Fahri", f_phone))
        conn.execute("INSERT INTO users (username, password_hash, display_name, phone_number) VALUES (?, ?, ?, ?)",
                     (m_user, generate_password_hash(m_pass, method='pbkdf2:sha256'), "Metin", m_phone))
        conn.commit()
        conn.close()
        flash("Kurulum tamamlandı. Lütfen giriş yapın.", "success")
        return redirect(url_for('login'))
        
    conn.close()
    return render_template_string("""{% extends 'base.html' %}
    {% block content %}
    <h2 class="mb-4 text-center">İlk Kurulum</h2>
    <form method="POST">
        <div class="card p-3">
            <h4>Yönetici (Fahri) Bilgileri</h4>
            <div class="mb-2"><input type="text" name="fahri_username" class="form-control" placeholder="Kullanıcı Adı" required></div>
            <div class="mb-2"><input type="password" name="fahri_password" class="form-control" placeholder="Şifre" required></div>
            <div class="mb-2"><input type="text" name="fahri_phone" class="form-control" placeholder="Telefon (örn: 5551234567)" required></div>
        </div>
        <div class="card p-3">
            <h4>Metin'in İletişim Bilgisi</h4>
            <div class="text-muted small mb-2">Metin için ayrı giriş yapılmayacak, sadece SMS gidecek ve borç takip edilecek.</div>
            <div class="mb-2"><input type="text" name="metin_phone" class="form-control" placeholder="Telefon (örn: 5551234567)" required></div>
        </div>
        <button type="submit" class="btn btn-primary w-100 py-2 fs-5">Kaydet</button>
    </form>
    {% endblock %}
    """)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        conn = database.get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password_hash'], password):
            login_user(User(dict(user)))
            return redirect(url_for('dashboard'))
        flash("Hatalı giriş, tekrar deneyin.", "danger")
    return render_template_string("""{% extends 'base.html' %}
    {% block content %}
    <div class="d-flex justify-content-center align-items-center" style="height: 80vh;">
        <div class="card p-4 shadow-sm" style="width: 100%; max-width: 400px;">
            <h3 class="text-center mb-4">Giriş Yap</h3>
            <form method="POST">
                <div class="mb-3"><input type="text" name="username" class="form-control form-control-lg" placeholder="Kullanıcı Adı" required></div>
                <div class="mb-3"><input type="password" name="password" class="form-control form-control-lg" placeholder="Şifre" required></div>
                <button type="submit" class="btn btn-primary btn-lg w-100">Giriş</button>
            </form>
        </div>
    </div>
    {% endblock %}
    """)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    conn = database.get_db_connection()
    today = datetime.now()
    
    # Tüm aktif faturaları çek
    all_bills = conn.execute("SELECT * FROM bills WHERE active = 1").fetchall()
    
    # Metin'in borcu
    fahri = conn.execute("SELECT id FROM users WHERE display_name = 'Fahri'").fetchone()
    metin = conn.execute("SELECT id FROM users WHERE display_name = 'Metin'").fetchone()
    metin_debt = 0
    if fahri and metin:
        debt_row = conn.execute("SELECT SUM(amount) as total FROM debts WHERE debtor_user_id = ? AND creditor_user_id = ? AND is_paid = 0", (metin['id'], fahri['id'])).fetchone()
        coll_row = conn.execute("SELECT SUM(amount) as total FROM debt_collections").fetchone()
        metin_debt = (debt_row['total'] or 0) - (coll_row['total'] or 0)

    # Banka Borcu Hesaplama (Dashboard için)
    bank_debt_row = conn.execute("SELECT SUM(current_balance) as total FROM cards WHERE active = 1 AND current_balance < 0").fetchone()
    total_bank_debt = abs(bank_debt_row['total'] or 0)

    payments = conn.execute('''
        SELECT p.*, b.name as bill_name, u.display_name as payer_name 
        FROM payments p 
        JOIN bills b ON p.bill_id = b.id 
        JOIN users u ON p.paid_by_user_id = u.id 
        ORDER BY p.payment_date DESC LIMIT 5
    ''').fetchall()
    
    dashboard_bills = []
    total_bills_amount = 0
    paid_bills_amount = 0
    
    for b in all_bills:
        # Hayalet fatura kontrolü: Tek seferlik faturaysa ve geçmişte ödenmişse gösterme
        if not b['is_recurring']:
            # Bu fatura için herhangi bir ödeme yapılmış mı?
            paid_ever = conn.execute("SELECT id FROM monthly_cycles WHERE bill_id = ? AND status = 'odendi'", (b['id'],)).fetchone()
            if paid_ever:
                # Eğer bu ay ödenmediyse (yani geçmişte ödenmiş ve bitmişse) gösterme
                paid_this_month = conn.execute("SELECT id FROM monthly_cycles WHERE bill_id = ? AND year = ? AND month = ? AND status = 'odendi'", 
                                              (b['id'], today.year, today.month)).fetchone()
                if not paid_this_month:
                    continue

        cycle = conn.execute("SELECT status FROM monthly_cycles WHERE bill_id = ? AND year = ? AND month = ?", (b['id'], today.year, today.month)).fetchone()
        
        total_bills_amount += b['amount']
        
        status_color = ""
        days_left = b['due_day'] - today.day
        
        is_paid = cycle and cycle['status'] == 'odendi'
        if is_paid:
            paid_bills_amount += b['amount']
            status_color = "success"
        elif days_left < 0 or days_left == 0:
            status_color = "danger"
        elif days_left <= 7:
            status_color = "warning"
        else:
            status_color = "light"
            
        dashboard_bills.append({
            'id': b['id'],
            'name': b['name'],
            'amount': b['amount'],
            'color': status_color,
            'days_left': days_left,
            'is_autopay': b['is_autopay']
        })
        
    remaining_bills_amount = total_bills_amount - paid_bills_amount
    conn.close()
    
    return render_template_string("""{% extends 'base.html' %}
    {% block content %}
    <div class="d-flex justify-content-between align-items-center mb-4">
        <span class="page-title">👋 Merhaba, {{ current_user.display_name }}</span>
        <a href="{{ url_for('ayarlar') }}" class="btn btn-sm" style="background:#f1f5f9;border-radius:10px;font-size:0.85rem;">⚙️ Ayarlar</a>
    </div>

    <div class="hero-card mb-4">
        <div class="label">Bu Ay Kalan Ödenecek</div>
        <div class="amount">{{ remaining_bills_amount|para }} ₺</div>
        
        <div class="d-flex justify-content-between mt-3 pt-2" style="border-top: 1px dotted rgba(255,255,255,0.4);">
            <div class="text-start">
                <div class="label" style="font-size:0.65rem; opacity:0.8;">Toplam Fatura</div>
                <div style="font-weight:600; font-size:1.1rem;">{{ total_bills_amount|para }} ₺</div>
            </div>
            <div class="text-end">
                <div class="label" style="font-size:0.65rem; opacity:0.8;">Ödenen</div>
                <div style="font-weight:600; font-size:1.1rem;">{{ paid_bills_amount|para }} ₺</div>
            </div>
        </div>
    </div>

    <div class="card mb-4 border-0 shadow-sm overflow-hidden" style="border-radius:20px; background: white;">
        <div class="d-flex align-items-center p-3" style="background: #fef2f2;">
            <div class="rounded-circle d-flex align-items-center justify-content-center" style="width:45px; height:45px; background: #fee2e2; color: #ef4444; font-size:1.2rem; margin-right:12px;">🏦</div>
            <div>
                <div class="stat-label" style="margin-bottom:0; color: #991b1b;">Bankalara Toplam Borç</div>
                <div style="font-weight:800; font-size:1.4rem; color: #dc2626;">{{ total_bank_debt|para }} ₺</div>
            </div>
        </div>
    </div>

    <div class="section-title">Bu Ay Faturalar (Tıkla ve Öde)</div>
    <div class="row g-2 mb-4">
        {% for b in dashboard_bills %}
        <div class="col-6">
            <a href="{{ url_for('odeme_kaydet', fatura_id=b.id) }}" class="text-decoration-none">
                <div class="bill-chip chip-{{ b.color }} position-relative">
                    {% if b.is_autopay %}<span class="badge" style="background:#6366f1;font-size:0.65rem;position:absolute;top:8px;right:8px;">OTO</span>{% endif %}
                    <div style="font-weight:600;font-size:0.9rem;">{{ b.name }}</div>
                    <div style="font-size:1.1rem;font-weight:700;">{{ b.amount|para }} ₺</div>
                    {% if b.color == 'success' %}
                        <div style="font-size:0.72rem;">✓ Ödendi</div>
                    {% else %}
                        {% if b.is_autopay %}
                            <a href="{{ url_for('oto_onayla', bill_id=b.id) }}" class="btn btn-sm btn-primary py-0 px-2 mt-1" style="font-size:0.65rem; border-radius:6px;" onclick="event.stopPropagation();">Onayla</a>
                        {% elif b.color == 'danger' %}
                            <div style="font-size:0.72rem;">⚠ Geçti</div>
                        {% elif b.color == 'warning' %}
                            <div style="font-size:0.72rem;">⏰ {{ b.days_left }} gün kaldı</div>
                        {% else %}
                            <div style="font-size:0.72rem;">{{ b.days_left }} gün</div>
                        {% endif %}
                    {% endif %}
                </div>
            </a>
        </div>
        {% else %}
        <div class="col-12"><div class="card p-4 text-center text-muted">Ödenecek fatura kalmadı! 🎉</div></div>
        {% endfor %}
    </div>

    <div class="section-title">Son Ödemeler</div>
    <div class="list-group shadow-sm" style="border-radius:14px;overflow:hidden;">
        {% for p in payments %}
        <div class="list-group-item">
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <div style="font-weight:600;font-size:0.95rem;">{{ p.bill_name }}</div>
                    <div style="font-size:0.8rem;color:var(--text-muted);">{{ p.payer_name }} · {{ p.card_used }} · {{ p.payment_date }}</div>
                </div>
                <div class="d-flex align-items-center gap-2">
                    <div style="font-weight:700;color:var(--success);">{{ p.amount|para }} ₺</div>
                    <form method="POST" action="{{ url_for('delete_payment', payment_id=p.id) }}" onsubmit="return confirm('Bu ödemeyi silmek istediğinize emin misiniz?');">
                        <button class="btn btn-sm" style="background:#fee2e2;color:#991b1b;border:none;border-radius:8px;padding:4px 8px;">✕</button>
                    </form>
                </div>
            </div>
        </div>
        {% else %}
        <div class="list-group-item text-center text-muted py-4">Henüz ödeme kaydı yok.</div>
        {% endfor %}
    </div>
    {% endblock %}
    """, 
    metin_debt=metin_debt, 
    dashboard_bills=dashboard_bills, 
    payments=payments,
    total_bills_amount=total_bills_amount,
    paid_bills_amount=paid_bills_amount,
    remaining_bills_amount=remaining_bills_amount,
    total_bank_debt=total_bank_debt)


@app.route('/oto_onayla/<int:bill_id>')
@login_required
def oto_onayla(bill_id):
    conn = database.get_db_connection()
    bill = conn.execute("SELECT * FROM bills WHERE id = ?", (bill_id,)).fetchone()
    
    if not bill:
        conn.close()
        flash("Fatura bulunamadı.", "danger")
        return redirect(url_for('dashboard'))
        
    if not bill['autopay_card_name']:
        conn.close()
        flash("Bu faturaya tanımlı otomatik ödeme kartı yok.", "warning")
        return redirect(url_for('dashboard'))
        
    # Kartı bul
    card = conn.execute("SELECT * FROM cards WHERE name = ?", (bill['autopay_card_name'],)).fetchone()
    if not card:
        conn.close()
        flash(f"'{bill['autopay_card_name']}' isimli kart bulunamadı.", "danger")
        return redirect(url_for('dashboard'))
        
    today = datetime.now()
    payment_date = today.strftime('%Y-%m-%d')
    
    # Ödemeyi kaydet
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO payments (bill_id, amount, payment_date, paid_by_user_id, card_used, note)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (bill_id, bill['amount'], payment_date, current_user.id, card['name'], "Otomatik ödeme onayı"))
    
    payment_id = cursor.lastrowid
    
    # Döngü kaydını güncelle veya ekle
    cycle_row = cursor.execute("SELECT id FROM monthly_cycles WHERE bill_id = ? AND year = ? AND month = ?", 
                          (bill_id, today.year, today.month)).fetchone()
    if cycle_row:
        cursor.execute("UPDATE monthly_cycles SET status = 'odendi', payment_id = ? WHERE id = ?", (payment_id, cycle_row['id']))
    else:
        cursor.execute("INSERT INTO monthly_cycles (bill_id, year, month, status, payment_id) VALUES (?, ?, ?, ?, ?)",
                      (bill_id, today.year, today.month, 'odendi', payment_id))
        
    # Kart bakiyesini düş (Borcu artır)
    cursor.execute("UPDATE cards SET current_balance = current_balance - ? WHERE id = ?", (bill['amount'], card['id']))
    
    # Borçlandırma Mantığı: Sadece kart sahibi Fahri ise Metin'e borç yaz
    if card['owner'] == 'Fahri':
        fahri = conn.execute("SELECT id FROM users WHERE display_name = 'Fahri'").fetchone()
        metin = conn.execute("SELECT id FROM users WHERE display_name = 'Metin'").fetchone()
        if fahri and metin:
            # Metin'e borç yaz ( debtor=Metin, creditor=Fahri )
            cursor.execute("INSERT INTO debts (debtor_user_id, creditor_user_id, amount, is_paid, payment_id) VALUES (?, ?, ?, ?, ?)",
                          (metin['id'], fahri['id'], bill['amount'], 0, payment_id))
    
    conn.commit()
    conn.close()
    
    # Bildirim
    msg = f"✅ {bill['name']} faturası {card['name']} ({card['owner']}) ile otomatik ödendi ve onaylandı. Tutar: {bill['amount']} TL"
    notifier.notify_all(msg)
    
    flash(f"{bill['name']} başarıyla onaylandı.", "success")
    return redirect(url_for('dashboard'))

@app.route('/fatura_duzenle/<int:bill_id>', methods=['GET', 'POST'])
@login_required
def fatura_duzenle(bill_id):
    conn = database.get_db_connection()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        amount_raw = request.form.get('amount') or '0'
        due_day = int(request.form.get('due_day') or 1)
        last_payment_day = int(request.form.get('last_payment_day') or 1)
        category = request.form.get('category') or 'Diğer'
        subscriber_no = request.form.get('subscriber_no', '')
        is_recurring = 1 if request.form.get('is_recurring') == 'on' else 0
        is_autopay = 1 if request.form.get('is_autopay') == 'on' else 0
        autopay_card_name = request.form.get('autopay_card_name', '') if is_autopay else ''
        
        if name:
            conn.execute('''
                UPDATE bills 
                SET name=?, amount=?, due_day=?, last_payment_day=?, category=?, 
                    is_recurring=?, is_autopay=?, subscriber_no=?, autopay_card_name=?
                WHERE id=?
            ''', (name, float(amount_raw), due_day, last_payment_day, category, 
                  is_recurring, is_autopay, subscriber_no, autopay_card_name, bill_id))
            conn.commit()
            flash("Fatura başarıyla güncellendi.", "success")
        else:
            flash("Fatura adı boş olamaz.", "danger")
        conn.close()
        return redirect(url_for('faturalar'))
        
    bill = conn.execute("SELECT * FROM bills WHERE id = ?", (bill_id,)).fetchone()
    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    cards = conn.execute("SELECT * FROM cards WHERE active = 1 ORDER BY owner, name").fetchall()
    conn.close()
    
    if not bill:
        flash("Fatura bulunamadı.", "danger")
        return redirect(url_for('faturalar'))
        
    return render_template_string("""{% extends 'base.html' %}
    {% block content %}
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h3>Fatura Düzenle</h3>
        <a href="{{ url_for('faturalar') }}" class="btn btn-outline-secondary">İptal</a>
    </div>
    <form method="POST" class="card p-4 shadow-sm border-0 mb-4">
        <div class="mb-3">
            <label class="form-label text-secondary fw-bold">Fatura Adı</label>
            <input type="text" name="name" class="form-control form-control-lg" value="{{ bill.name }}" required>
        </div>
        <div class="mb-3">
            <label class="form-label text-secondary fw-bold">Abone / Müşteri Numarası</label>
            <input type="text" name="subscriber_no" class="form-control" value="{{ bill.subscriber_no }}">
        </div>
        <div class="mb-3">
            <label class="form-label text-secondary fw-bold">Tutar (Opsiyonel Sabit Tutar)</label>
            <input type="number" step="0.01" name="amount" class="form-control form-control-lg" value="{{ bill.amount }}">
        </div>
        
        <div class="row g-2 mb-3">
            <div class="col-6">
                <label class="form-label text-secondary fw-bold">Normal Ödeme Günü</label>
                <input type="number" name="due_day" class="form-control" min="1" max="31" value="{{ bill.due_day }}" required>
            </div>
            <div class="col-6">
                <label class="form-label text-secondary fw-bold">Son Ödeme Günü</label>
                <input type="number" name="last_payment_day" class="form-control" min="1" max="31" value="{{ bill.last_payment_day }}" required>
            </div>
        </div>
        
        <div class="mb-3">
            <label class="form-label text-secondary fw-bold">Kategori</label>
            <select name="category" class="form-select">
                {% for c in categories %}
                <option value="{{ c.name }}" {% if c.name == bill.category %}selected{% endif %}>{{ c.name }}</option>
                {% endfor %}
            </select>
        </div>
        
        <div class="d-flex flex-column gap-3 mb-4 mt-2">
            <div class="form-check form-switch">
                <input class="form-check-input" type="checkbox" name="is_recurring" id="rec2" {% if bill.is_recurring %}checked{% endif %}>
                <label class="form-check-label fw-bold" for="rec2">Her Ay Tekrarla</label>
            </div>
            <div class="form-check form-switch">
                <input class="form-check-input" type="checkbox" name="is_autopay" id="auto2" {% if bill.is_autopay %}checked{% endif %} onchange="toggleAutopayCardEdit(this)">
                <label class="form-check-label fw-bold" for="auto2">Otomatik Ödeniyor</label>
            </div>
        </div>

        <div class="mb-4" id="autopay_card_container_edit" style="{% if not bill.is_autopay %}display:none;{% endif %}">
            <label class="form-label text-secondary fw-bold">Hangi Karttan Çekilecek?</label>
            <select name="autopay_card_name" class="form-select">
                <option value="">Kart Seçin...</option>
                {% for c in cards %}
                <option value="{{ c.name }} ({{ c.owner }})" {% if bill.autopay_card_name == (c.name + ' (' + c.owner + ')') %}selected{% endif %}>{{ c.name }} ({{ c.owner }})</option>
                {% endfor %}
            </select>
        </div>

        <button type="submit" class="btn btn-primary btn-lg w-100 py-3 fw-bold">Güncelle</button>
    </form>
    <script>
        function toggleAutopayCardEdit(el) {
            document.getElementById('autopay_card_container_edit').style.display = el.checked ? 'block' : 'none';
        }
    </script>
    {% endblock %}
    """, bill=bill, categories=categories, cards=cards)

@app.route('/faturalar', methods=['GET', 'POST'])
@login_required
def faturalar():
    conn = database.get_db_connection()
    if request.method == 'POST':
        if 'delete_id' in request.form:
            conn.execute("UPDATE bills SET active = 0 WHERE id = ?", (request.form.get('delete_id'),))
            flash("Fatura silindi.", "success")
        else:
            name = request.form.get('name', '').strip()
            amount_raw = request.form.get('amount') or '0'
            due_day = int(request.form.get('due_day') or 1)
            last_payment_day = int(request.form.get('last_payment_day') or 1)
            category = request.form.get('category') or 'Diğer'
            subscriber_no = request.form.get('subscriber_no', '')
            is_recurring = 1 if request.form.get('is_recurring') == 'on' else 0
            is_autopay = 1 if request.form.get('is_autopay') == 'on' else 0
            autopay_card_name = request.form.get('autopay_card_name', '') if is_autopay else ''

            if not name:
                flash("Fatura adı boş olamaz.", "danger")
            else:
                amount = float(amount_raw)
                conn.execute('''
                    INSERT INTO bills (name, owner, amount, due_day, last_payment_day, category, is_recurring, is_autopay, subscriber_no, autopay_card_name)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (name, "Ortak", amount, due_day, last_payment_day, category, is_recurring, is_autopay, subscriber_no, autopay_card_name))
                flash("Fatura başarıyla eklendi.", "success")
        conn.commit()
        return redirect(url_for('faturalar'))
        
    bills_raw = conn.execute("SELECT * FROM bills WHERE active = 1 ORDER BY category, name").fetchall()
    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    cards = conn.execute("SELECT * FROM cards WHERE active = 1 ORDER BY owner, name").fetchall()
    
    # Gruplandırma
    bills_grouped = {}
    for b in bills_raw:
        cat = b['category']
        if cat not in bills_grouped:
            bills_grouped[cat] = []
        bills_grouped[cat].append(b)

    conn.close()
    
    return render_template_string("""{% extends 'base.html' %}
    {% block content %}
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h3>Faturalar</h3>
        <div>
            <a href="{{ url_for('kategoriler') }}" class="btn btn-outline-secondary me-2">Kategoriler</a>
            <button class="btn btn-primary px-4 fw-bold shadow-sm" data-bs-toggle="modal" data-bs-target="#addBillModal">+ Ekle</button>
        </div>
    </div>
    
    {% for cat, items in bills_grouped.items() %}
    <div class="section-title mt-4 mb-2" style="font-size:1.1rem; color:var(--primary); border-bottom:2px solid #e2e8f0; padding-bottom:5px;">{{ cat }}</div>
    {% for b in items %}
    <div class="card p-3 shadow-sm mb-3">
        <div class="d-flex justify-content-between align-items-start">
            <div>
                <h5 class="mb-0">{{ b.name }}</h5>
                {% if b.subscriber_no %}<div style="font-size:0.78rem;color:var(--text-muted);">Abone No: <strong>{{ b.subscriber_no }}</strong></div>{% endif %}
                <div class="mt-1">
                    {% if b.is_autopay %}<span class="badge" style="background:#6366f1;">Otomatik: {{ b.autopay_card_name }}</span>{% endif %}
                    {% if b.is_recurring %}<span class="badge bg-light text-muted">Tekrarlı</span>{% else %}<span class="badge bg-warning text-dark">Tek Seferlik</span>{% endif %}
                </div>
            </div>
            <div class="d-inline-flex gap-2">
                <a href="{{ url_for('fatura_duzenle', bill_id=b.id) }}" class="btn btn-sm" style="background:#e0f2fe;color:#0369a1;border:none;border-radius:8px;padding:4px 10px;">Düzenle</a>
                <form method="POST" onsubmit="return confirm('Bu faturasını silmek istediğinize emin misiniz?');" style="margin:0;">
                    <input type="hidden" name="delete_id" value="{{ b.id }}">
                    <button class="btn btn-sm" style="background:#fee2e2;color:#991b1b;border:none;border-radius:8px;padding:4px 10px;">Sil</button>
                </form>
            </div>
        </div>
        <div class="d-flex justify-content-between align-items-end mt-3" style="background:#f8fafc;border-radius:10px;padding:10px 12px;">
            <div class="small">
                <div>Ödeme Günü: <strong>Ayın {{ b.due_day }}. günü</strong></div>
                <div>Son Gün: <strong style="color:var(--danger);">Ayın {{ b.last_payment_day }}. günü</strong></div>
            </div>
            <div style="font-weight:700;font-size:1.4rem;color:var(--primary);">{{ b.amount|para }} ₺</div>
        </div>
    </div>
    {% endfor %}
    {% else %}
    <div class="text-center text-muted p-5 bg-white rounded shadow-sm">
        <h4>Henüz fatura yok.</h4>
        <p>Sağ üstteki butondan yeni fatura ekleyebilirsiniz.</p>
    </div>
    {% endfor %}
    
    <!-- Ekle Modal -->
    <div class="modal fade" id="addBillModal" tabindex="-1">
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <form method="POST">
              <div class="modal-header border-0 pb-0">
                <h5 class="modal-title fw-bold">Yeni Fatura Ekle</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
              </div>
              <div class="modal-body">
                <div class="mb-3"><input type="text" name="name" class="form-control form-control-lg" placeholder="Fatura Adı" required></div>
                <div class="mb-3"><input type="text" name="subscriber_no" class="form-control" placeholder="Abone / Müşteri Numarası (opsiyonel)"></div>
                <div class="mb-3"><input type="number" step="0.01" name="amount" class="form-control form-control-lg" placeholder="Varsayılan Tutar (Opsiyonel)"></div>
                <div class="row">
                    <div class="col-6 mb-3"><input type="number" name="due_day" class="form-control" placeholder="Ödeme Günü (1-31)" required min="1" max="31"></div>
                    <div class="col-6 mb-3"><input type="number" name="last_payment_day" class="form-control" placeholder="Son Gün (1-31)" required min="1" max="31"></div>
                </div>
                <div class="mb-3">
                    <label class="form-label text-secondary fw-bold">Kategori Seçin</label>
                    <div class="row g-2">
                        {% for cat in categories %}
                        <div class="col-6">
                            <input type="radio" class="btn-check btn-check-custom" name="category" id="cat_{{ cat.id }}" value="{{ cat.name }}" required>
                            <label class="btn btn-outline-primary w-100 py-2" for="cat_{{ cat.id }}">{{ cat.name }}</label>
                        </div>
                        {% endfor %}
                    </div>
                </div>
                <div class="form-check form-switch fs-5 mb-2 mt-3">
                  <input class="form-check-input" type="checkbox" name="is_recurring" id="is_recurring" checked>
                  <label class="form-check-label" for="is_recurring">Her ay tekrarlar</label>
                </div>
                <div class="form-check form-switch fs-5">
                  <input class="form-check-input" type="checkbox" name="is_autopay" id="is_autopay" onchange="toggleAutopayCard(this)">
                  <label class="form-check-label text-danger" for="is_autopay">Otomatik Ödemede</label>
                </div>
                <div class="mb-3 mt-2" id="autopay_card_container" style="display:none;">
                    <label class="form-label text-secondary fw-bold small">Hangi Karttan Çekilecek?</label>
                    <select name="autopay_card_name" class="form-select">
                        <option value="">Kart Seçin...</option>
                        {% for c in cards %}
                        <option value="{{ c.name }} ({{ c.owner }})">{{ c.name }} ({{ c.owner }})</option>
                        {% endfor %}
                    </select>
                </div>
              </div>
              <div class="modal-footer border-0 pt-0 mt-3">
                <button type="submit" class="btn btn-primary w-100 py-3 fs-5 fw-bold shadow">Kaydet</button>
              </div>
          </form>
        </div>
      </div>
    </div>
    <script>
        function toggleAutopayCard(el) {
            document.getElementById('autopay_card_container').style.display = el.checked ? 'block' : 'none';
        }
    </script>
    {% endblock %}
    """, bills_grouped=bills_grouped, categories=categories, cards=cards)

@app.route('/delete_payment/<int:payment_id>', methods=['POST'])
@login_required
def delete_payment(payment_id):
    conn = database.get_db_connection()
    payment = conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
    if payment:
        p = dict(payment)
        dt = datetime.strptime(p['payment_date'], '%Y-%m-%d')
        conn.execute("DELETE FROM debts WHERE payment_id = ?", (payment_id,))
        conn.execute("UPDATE monthly_cycles SET status = 'bekliyor', payment_id = NULL WHERE payment_id = ?", (payment_id,))
        conn.execute("DELETE FROM payments WHERE id = ?", (payment_id,))
        conn.commit()
        flash("Ödeme silindi ve ilgili borç kayıtları temizlendi.", "success")
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/kategoriler', methods=['GET', 'POST'])
@login_required
def kategoriler():
    conn = database.get_db_connection()
    if request.method == 'POST':
        if 'delete_id' in request.form:
            conn.execute("DELETE FROM categories WHERE id = ?", (request.form.get('delete_id'),))
            flash("Kategori silindi.", "success")
        elif 'edit_id' in request.form:
            new_name = request.form.get('name')
            old_name_row = conn.execute("SELECT name FROM categories WHERE id = ?", (request.form.get('edit_id'),)).fetchone()
            if old_name_row and new_name:
                conn.execute("UPDATE categories SET name = ? WHERE id = ?", (new_name, request.form.get('edit_id')))
                conn.execute("UPDATE bills SET category = ? WHERE category = ?", (new_name, old_name_row['name']))
                flash("Kategori ve bağlı faturalar güncellendi.", "success")
        else:
            name = request.form.get('name')
            try:
                conn.execute("INSERT INTO categories (name) VALUES (?)", (name,))
                flash("Kategori eklendi.", "success")
            except:
                flash("Bu kategori zaten var.", "danger")
        conn.commit()
        return redirect(url_for('kategoriler'))
        
    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    conn.close()
    
    return render_template_string("""{% extends 'base.html' %}
    {% block content %}
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h3>Kategoriler</h3>
        <a href="{{ url_for('faturalar') }}" class="btn btn-outline-secondary">Geri Dön</a>
    </div>
    
    <form method="POST" class="card p-4 shadow-sm mb-4 border-0 bg-light">
        <h5 class="mb-3">Yeni Kategori Ekle</h5>
        <div class="input-group input-group-lg">
            <input type="text" name="name" class="form-control" placeholder="Kategori Adı" required>
            <button class="btn btn-primary px-4 fw-bold" type="submit">Ekle</button>
        </div>
    </form>
    
    <div class="list-group shadow-sm">
        {% for cat in categories %}
        <div class="list-group-item d-flex justify-content-between align-items-center p-3">
            <span class="fs-5">{{ cat.name }}</span>
            <div class="d-flex gap-2">
                <button class="btn btn-sm btn-outline-primary" data-bs-toggle="modal" data-bs-target="#editCat{{ cat.id }}">Düzenle</button>
                <form method="POST" onsubmit="return confirm('Silmek istediğinize emin misiniz?');" style="margin:0;">
                    <input type="hidden" name="delete_id" value="{{ cat.id }}">
                    <button class="btn btn-sm btn-outline-danger">Sil</button>
                </form>
            </div>
        </div>

        <!-- Düzenle Modal -->
        <div class="modal fade" id="editCat{{ cat.id }}" tabindex="-1">
          <div class="modal-dialog modal-dialog-centered">
            <div class="modal-content">
              <form method="POST">
                  <input type="hidden" name="edit_id" value="{{ cat.id }}">
                  <div class="modal-header border-0">
                    <h5 class="modal-title fw-bold">Kategori Düzenle</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                  </div>
                  <div class="modal-body">
                    <input type="text" name="name" class="form-control form-control-lg" value="{{ cat.name }}" required>
                  </div>
                  <div class="modal-footer border-0">
                    <button type="submit" class="btn btn-primary w-100 py-3 fw-bold">Güncelle</button>
                  </div>
              </form>
            </div>
          </div>
        </div>
        {% endfor %}
    </div>
    {% endblock %}
    """, categories=categories)

@app.route('/odeme-kaydet', methods=['GET', 'POST'])
@login_required
def odeme_kaydet():
    conn = database.get_db_connection()
    if request.method == 'POST':
        bill_id = request.form.get('bill_id')
        amount = float(request.form.get('amount'))
        card_id = request.form.get('card_id')
        payment_date = request.form.get('payment_date')
        notes = request.form.get('notes', '')
        
        card_row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        bill_row  = conn.execute("SELECT * FROM bills WHERE id = ?", (bill_id,)).fetchone()

        if not card_row or not bill_row:
            conn.close()
            flash("Hata: Kart veya fatura bulunamadı.", "danger")
            return redirect(url_for('odeme_kaydet'))

        card = dict(card_row)
        bill  = dict(bill_row)
        card_used = f"{card['name']} ({card['owner']})"
        
        fahri = conn.execute("SELECT * FROM users WHERE display_name = 'Fahri'").fetchone()
        metin = conn.execute("SELECT * FROM users WHERE display_name = 'Metin'").fetchone()
        
        # Payer is determined by card owner
        if card['owner'] == 'Fahri':
            payer = fahri
        elif card['owner'] == 'Metin':
            payer = metin
        else:
            payer = fahri # Default to Fahri for shared cards
        
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO payments (bill_id, paid_by_user_id, paid_for_owner, amount, card_used, payment_date, is_on_behalf, notes)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        ''', (bill_id, payer['id'], "Ortak", amount, card_used, payment_date, notes))
        payment_id = cursor.lastrowid
        
        debt_amount = 0
        if card['owner'] == 'Fahri' and metin:
            cursor.execute('''
                INSERT INTO debts (payment_id, debtor_user_id, creditor_user_id, amount, is_paid)
                VALUES (?, ?, ?, ?, 0)
            ''', (payment_id, metin['id'], fahri['id'], amount))
            debt_amount = amount
                
        dt = datetime.strptime(payment_date, '%Y-%m-%d')
        bill_month = int(request.form.get('bill_month', dt.month))
        bill_year = int(request.form.get('bill_year', dt.year))
        
        existing_cycle = conn.execute("SELECT id FROM monthly_cycles WHERE bill_id = ? AND year = ? AND month = ?",
                                     (bill_id, bill_year, bill_month)).fetchone()
        if existing_cycle:
            conn.execute("UPDATE monthly_cycles SET status = 'odendi', payment_id = ? WHERE bill_id = ? AND year = ? AND month = ?",
                         (payment_id, bill_id, bill_year, bill_month))
        else:
            conn.execute("INSERT INTO monthly_cycles (bill_id, year, month, status, payment_id) VALUES (?, ?, ?, 'odendi', ?)",
                         (bill_id, bill_year, bill_month, payment_id))
        
        conn.commit()
        
        msg = f"✅ *{card_used}* ile ödendi: *{bill['name']}* ({bill['category']})\n📅 *Dönem:* {bill_month}/{bill_year}\n💰 *Tutar:* {amount}TL"
        
        if debt_amount > 0 and metin and fahri:
            total_debt_row = conn.execute("SELECT SUM(amount) as t FROM debts WHERE debtor_user_id = ? AND creditor_user_id = ? AND is_paid = 0", (metin['id'], fahri['id'])).fetchone()
            coll_row = conn.execute("SELECT SUM(amount) as total FROM debt_collections").fetchone()
            total_debt = (total_debt_row['t'] or 0) - (coll_row['total'] or 0)
            msg += f"\n💸 Metin'e borç yazıldı: +{amount}TL\n🤝 Güncel Toplam Borç: {format_para(total_debt)} TL"
            
        notifier.notify_all(msg)
        
        flash("Ödeme başarıyla kaydedildi ve WhatsApp bildirimi gönderildi.", "success")
        return redirect(url_for('odeme_kaydet'))
        
    fatura_id = request.args.get('fatura_id')
    bills = conn.execute("SELECT * FROM bills WHERE active = 1").fetchall()
    cards = conn.execute("SELECT * FROM cards WHERE active = 1 ORDER BY owner, name").fetchall()
    month_names = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
    today = datetime.now()
    conn.close()
    
    return render_template_string("""{% extends 'base.html' %}
    {% block content %}
    <h3 class="mb-4">Ödeme Kaydet</h3>
    <form method="POST" class="card p-4 shadow-sm border-0">
        <div class="mb-4">
            <label class="form-label fw-bold text-secondary">Hangi Fatura?</label>
            <select name="bill_id" id="bill_id" class="form-select form-select-lg" required onchange="updateAmount()">
                <option value="">Fatura Seçiniz...</option>
                {% for b in bills %}
                <option value="{{ b.id }}" data-amount="{{ b.amount }}" {% if fatura_id|string == b.id|string %}selected{% endif %}>{{ b.name }}</option>
                {% endfor %}
            </select>
        </div>
        
        <div class="row g-2 mb-4">
            <div class="col-6">
                <label class="form-label fw-bold text-secondary">Faturanın Ait Olduğu Ay</label>
                <select name="bill_month" class="form-select form-select-lg">
                    {% for m in range(1, 13) %}
                    <option value="{{ m }}" {% if m == today.month %}selected{% endif %}>{{ month_names[m] }}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="col-6">
                <label class="form-label fw-bold text-secondary">Fatura Yılı</label>
                <input type="number" name="bill_year" class="form-control form-control-lg" value="{{ today.year }}">
            </div>
        </div>

        <div class="mb-4">
            <label class="form-label fw-bold text-secondary">Tutar (TL)</label>
            <div class="input-group input-group-lg">
                <span class="input-group-text">₺</span>
                <input type="number" step="0.01" name="amount" id="amount" class="form-control" required>
            </div>
        </div>

        <div class="mb-4">
            <label class="form-label fw-bold text-secondary">Hangi Kart Kullanıldı?</label>
            <select name="card_id" class="form-select form-select-lg" required>
                <option value="">Kart Seçiniz...</option>
                {% for c in cards %}
                <option value="{{ c.id }}">{{ c.name }} ({{ c.owner }})</option>
                {% endfor %}
            </select>
            <div class="form-text mt-2 text-primary">Sadece 'Fahri'ye ait kartlar Metin'e borç yazdırır.</div>
        </div>
        
        <div class="mb-4">
            <label class="form-label fw-bold text-secondary">Ödeme Tarihi (Bugün)</label>
            <input type="date" name="payment_date" id="payment_date" class="form-control form-control-lg" required>
        </div>
        <div class="mb-4">
            <label class="form-label fw-bold text-secondary">Notlar (Opsiyonel)</label>
            <textarea name="notes" class="form-control" rows="2" placeholder="Ekstra bir not ekleyebilirsiniz..."></textarea>
        </div>
        <button type="submit" class="btn btn-success btn-lg w-100 py-3 fw-bold shadow">ÖDEMEYİ KAYDET</button>
    </form>
    {% endblock %}
    
    {% block scripts %}
    <script>
        document.getElementById('payment_date').valueAsDate = new Date();
        
        function updateAmount() {
            var select = document.getElementById('bill_id');
            var amount = select.options[select.selectedIndex].getAttribute('data-amount');
            if(amount && amount > 0) {
                document.getElementById('amount').value = amount;
            }
        }
        // Sayfa yüklendiğinde fatura seçiliyse tutarı güncelle
        window.onload = updateAmount;
    </script>
    {% endblock %}
    """, bills=bills, cards=cards, today=today, month_names=month_names, fatura_id=fatura_id)

@app.route('/borclar', methods=['GET', 'POST'])
@login_required
def borclar():
    conn = database.get_db_connection()
    metin = conn.execute("SELECT * FROM users WHERE display_name = 'Metin'").fetchone()
    fahri = conn.execute("SELECT * FROM users WHERE display_name = 'Fahri'").fetchone()
    
    if not metin or not fahri:
        conn.close()
        return "Sistemde Fahri ve Metin kullanıcıları bulunamadı."
        
    if request.method == 'POST':
        debt_id = request.form.get('debt_id')
        cursor = conn.cursor()
        cursor.execute("UPDATE debts SET is_paid = 1, paid_date = ? WHERE id = ?", (datetime.now().strftime('%Y-%m-%d'), debt_id))
        conn.commit()
        
        debt = conn.execute("SELECT amount FROM debts WHERE id = ?", (debt_id,)).fetchone()
        total_row = conn.execute("SELECT SUM(amount) as t FROM debts WHERE debtor_user_id = ? AND creditor_user_id = ? AND is_paid = 0", (metin['id'], fahri['id'])).fetchone()
        total = total_row['t'] or 0
        
        msg = f"✅ Metin {debt['amount']}TL borcunu kapatti. Kalan borc: {total}TL"
        notifier.notify_all(msg)
        
        flash("Borç ödendi olarak işaretlendi ve SMS gönderildi.", "success")
        return redirect(url_for('borclar'))
        
    debts = conn.execute('''
        SELECT d.*, p.payment_date, b.name as bill_name, mc.year as bill_year, mc.month as bill_month
        FROM debts d
        LEFT JOIN payments p ON d.payment_id = p.id
        LEFT JOIN bills b ON p.bill_id = b.id
        LEFT JOIN monthly_cycles mc ON p.id = mc.payment_id
        WHERE d.debtor_user_id = ? AND d.creditor_user_id = ? AND d.is_paid = 0
        ORDER BY d.id DESC
    ''', (metin['id'], fahri['id'])).fetchall()
    
    total_debt_row = conn.execute("SELECT SUM(amount) as t FROM debts WHERE debtor_user_id = ? AND creditor_user_id = ? AND is_paid = 0", (metin['id'], fahri['id'])).fetchone()
    coll_row = conn.execute("SELECT SUM(amount) as total FROM debt_collections").fetchone()
    total = (total_debt_row['t'] or 0) - (coll_row['total'] or 0)
    
    conn.close()
    
    return render_template_string("""{% extends 'base.html' %}
    {% block content %}
    <h3 class="mb-4">Borç Takibi</h3>
    
    <!-- Tahsilat (Para Alındı) Formu -->
    <div class="card p-3 mb-4 border-0 shadow-sm" style="background: #e0f2fe; border-left: 5px solid #0369a1 !important;">
        <h6 class="fw-bold mb-2 text-primary">💰 {% if current_user.display_name == 'Fahri' %}Metin'den Para Alındı{% else %}Fahri'ye Para Verildi{% endif %} (Tahsilat)</h6>
        <form action="{{ url_for('tahsilat_ekle') }}" method="POST" class="row g-2">
            <div class="col-8">
                <input type="text" name="note" class="form-control" placeholder="Açıklama (opsiyonel)">
            </div>
            <div class="col-4">
                <div class="input-group">
                    <span class="input-group-text">₺</span>
                    <input type="number" step="0.01" name="amount" class="form-control" placeholder="Tutar" required>
                </div>
            </div>
            <div class="col-12">
                <button type="submit" class="btn btn-primary w-100 btn-sm fw-bold">TAHSİLAT KAYDET</button>
            </div>
        </form>
    </div>

    <!-- Manuel Borç Ekleme -->
    <div class="card p-3 mb-4 border-0 shadow-sm bg-light">
        <h6 class="fw-bold mb-2">➕ Manuel Borç Ekle ({% if current_user.display_name == 'Fahri' %}Metin'e Yaz{% else %}Kendime Yaz{% endif %})</h6>
        <form action="{{ url_for('manuel_borc_ekle') }}" method="POST" class="row g-2">
            <div class="col-8">
                <input type="text" name="reason" class="form-control" placeholder="Borç Nedeni (örn: Yemek, Market)" required>
            </div>
            <div class="col-4">
                <input type="number" step="0.01" name="amount" class="form-control" placeholder="Tutar" required>
            </div>
            <div class="col-12">
                <button type="submit" class="btn btn-danger w-100 btn-sm fw-bold">BORÇ YAZ</button>
            </div>
        </form>
    </div>

    <div class="card p-4 mb-4 text-center bg-danger text-white shadow-lg border-0" style="background: linear-gradient(135deg, #dc3545, #b02a37);">
        <h5 class="opacity-75">{% if current_user.display_name == 'Fahri' %}Metin'in Güncel Kalan Borcu{% else %}Fahri'ye Güncel Kalan Borcum{% endif %}</h5>
        <div class="dashboard-debt" style="font-size: 3.5rem;">{{ total|para }} TL</div>
    </div>
    
    <h5 class="text-secondary mb-3">Bekleyen Borç Kalemleri</h5>
    <div class="list-group shadow-sm">
        {% for d in debts %}
        <div class="list-group-item list-group-item-action d-flex justify-content-between align-items-center p-3 border-start border-4 border-danger">
            <div class="d-flex align-items-center gap-3">
                <form method="POST" action="{{ url_for('delete_debt', debt_id=d.id) }}" onsubmit="return confirm('Bu borç kaydını tamamen silmek istiyor musunuz?');" style="margin:0;">
                    <button class="btn btn-sm" style="background:#fee2e2;color:#991b1b;border:none;border-radius:8px;padding:4px 8px;">✕</button>
                </form>
                <div>
                    <h5 class="mb-1 fw-bold">{{ d.bill_name if d.bill_name else 'Manuel Borç' }} {% if d.bill_month %}<span class="badge bg-secondary fs-6 ms-2" style="font-weight:500;">{{ d.bill_month }}/{{ d.bill_year }}</span>{% endif %}</h5>
                    <small class="text-muted d-block mb-1">{{ d.payment_date if d.payment_date else 'Özel Kayıt' }}</small>
                    <div class="fw-bold fs-5 text-danger">{{ d.amount|para }} TL</div>
                </div>
            </div>
            <form method="POST" onsubmit="return confirm('Bu borcu ödendi olarak işaretlemek istiyor musunuz? Geri alınamaz!');">
                <input type="hidden" name="debt_id" value="{{ d.id }}">
                <button class="btn btn-success btn-lg shadow-sm">Ödendi ✓</button>
            </form>
        </div>
        {% else %}
        <div class="list-group-item text-center text-muted p-5 bg-white rounded">
            <h1 class="display-1 text-success mb-3">🎉</h1>
            <h4>Bekleyen borç bulunmuyor.</h4>
            <p>Her şey tertemiz!</p>
        </div>
        {% endfor %}
    </div>
    {% endblock %}
    """, debts=debts, total=total)

@app.route('/delete_debt/<int:debt_id>', methods=['POST'])
@login_required
def delete_debt(debt_id):
    conn = database.get_db_connection()
    conn.execute("DELETE FROM debts WHERE id = ?", (debt_id,))
    conn.commit()
    conn.close()
    flash("Borç kaydı silindi.", "success")
    return redirect(url_for('borclar'))

@app.route('/manuel_borc_ekle', methods=['POST'])
@login_required
def manuel_borc_ekle():
    amount = float(request.form.get('amount'))
    reason = request.form.get('reason')
    
    conn = database.get_db_connection()
    metin = conn.execute("SELECT id FROM users WHERE display_name = 'Metin'").fetchone()
    fahri = conn.execute("SELECT id FROM users WHERE display_name = 'Fahri'").fetchone()
    
    if metin and fahri:
        # payment_id=0 veya NULL (Postgres'te esnettik)
        conn.execute('''
            INSERT INTO debts (payment_id, debtor_user_id, creditor_user_id, amount, is_paid)
            VALUES (?, ?, ?, ?, 0)
        ''', (0, metin['id'], fahri['id'], amount))
        conn.commit()
        
        total_row = conn.execute("SELECT SUM(amount) as t FROM debts WHERE debtor_user_id = ? AND creditor_user_id = ? AND is_paid = 0", (metin['id'], fahri['id'])).fetchone()
        total = total_row['t'] or 0
        
        msg = f"💸 *MANUEL BORÇ KAYDI*\nMetin, Fahri sana bir borç yazdı.\n*Neden:* {reason}\n*Tutar:* {format_para(amount)} TL\n*Toplam Borcun:* {format_para(total)} TL"
        notifier.notify_all(msg)
        flash("Manuel borç eklendi.", "success")
        
    conn.close()
    return redirect(url_for('borclar'))

@app.route('/tahsilat_ekle', methods=['POST'])
@login_required
def tahsilat_ekle():
    amount = float(request.form.get('amount'))
    note = request.form.get('note', '')
    
    conn = database.get_db_connection()
    conn.execute('''
        INSERT INTO debt_collections (amount, collection_date, note)
        VALUES (?, ?, ?)
    ''', (amount, datetime.now().strftime('%Y-%m-%d'), note))
    conn.commit()
    
    # Yeni borç hesapla
    metin = conn.execute("SELECT id FROM users WHERE display_name = 'Metin'").fetchone()
    fahri = conn.execute("SELECT id FROM users WHERE display_name = 'Fahri'").fetchone()
    
    total = 0
    if metin and fahri:
        debt_row = conn.execute("SELECT SUM(amount) as t FROM debts WHERE debtor_user_id = ? AND creditor_user_id = ? AND is_paid = 0", (metin['id'], fahri['id'])).fetchone()
        coll_row = conn.execute("SELECT SUM(amount) as total FROM debt_collections").fetchone()
        total = (debt_row['t'] or 0) - (coll_row['total'] or 0)
    
    msg = f"💰 *TAHSİLAT ALINDI*\nMetin {format_para(amount)} TL ödeme yaptı.\n*Not:* {note if note else '-'}\n📉 *Güncel Kalan Borç:* {format_para(total)} TL"
    notifier.notify_all(msg)
    
    conn.close()
    flash("Tahsilat başarıyla kaydedildi.", "success")
    return redirect(url_for('borclar'))

@app.route('/takvim')
@login_required
def takvim():
    year = int(request.args.get('year', datetime.now().year))
    month = int(request.args.get('month', datetime.now().month))
    
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    
    cal = calendar.monthcalendar(year, month)
    
    conn = database.get_db_connection()
    bills = conn.execute("SELECT * FROM bills WHERE active = 1").fetchall()
    
    monthly_data = {}
    for b in bills:
        cycle = conn.execute("SELECT status FROM monthly_cycles WHERE bill_id = ? AND year = ? AND month = ?", (b['id'], year, month)).fetchone()
        status = cycle['status'] if cycle else 'bekliyor'
        
        css_class = "warning"
        if status == 'odendi':
            css_class = "success"
        else:
            today = datetime.now()
            if year < today.year or (year == today.year and month < today.month) or (year == today.year and month == today.month and b['due_day'] < today.day):
                css_class = "danger"
                
        day = b['due_day']
        if day not in monthly_data:
            monthly_data[day] = []
        monthly_data[day].append({
            'name': b['name'],
            'amount': b['amount'],
            'css_class': css_class
        })
    conn.close()
    
    month_names = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
    
    return render_template_string("""{% extends 'base.html' %}
    {% block content %}
    <div class="d-flex justify-content-between align-items-center mb-4 bg-white p-3 rounded shadow-sm">
        <a href="{{ url_for('takvim', year=prev_year, month=prev_month) }}" class="btn btn-outline-primary fw-bold px-3">&laquo; Geri</a>
        <h4 class="mb-0 fw-bold text-primary">{{ month_names[month] }} {{ year }}</h4>
        <a href="{{ url_for('takvim', year=next_year, month=next_month) }}" class="btn btn-outline-primary fw-bold px-3">İleri &raquo;</a>
    </div>
    
    <div class="table-responsive bg-white rounded shadow-sm p-2">
        <table class="table table-bordered calendar-table mb-0">
            <thead class="table-light">
                <tr>
                    <th class="text-danger">Pzt</th><th>Sal</th><th>Çar</th><th>Per</th><th>Cum</th><th>Cts</th><th class="text-danger">Paz</th>
                </tr>
            </thead>
            <tbody>
                {% for week in cal %}
                <tr>
                    {% for day in week %}
                    <td class="{{ 'bg-light' if day == 0 else '' }}">
                        {% if day != 0 %}
                        <div class="day-number text-end mb-1 text-secondary">{{ day }}</div>
                        {% if day in monthly_data %}
                            {% for item in monthly_data[day] %}
                            <div class="cal-item {{ item.css_class }} shadow-sm">
                                <div class="text-truncate fw-bold">{{ item.name }}</div>
                                <div>{{ item.amount|para }}</div>
                            </div>
                            {% endfor %}
                        {% endif %}
                        {% endif %}
                    </td>
                    {% endfor %}
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    <div class="mt-4 p-3 bg-white rounded shadow-sm d-flex justify-content-center gap-3">
        <span class="badge bg-success fs-6 px-3 py-2">✓ Ödendi</span>
        <span class="badge bg-warning text-dark fs-6 px-3 py-2">⌛ Bekliyor</span>
        <span class="badge bg-danger fs-6 px-3 py-2">⚠ Geçmiş</span>
    </div>
    {% endblock %}
    """, cal=cal, year=year, month=month, prev_year=prev_year, prev_month=prev_month, next_year=next_year, next_month=next_month, monthly_data=monthly_data, month_names=month_names)

@app.route('/raporlar', methods=['GET', 'POST'])
@login_required
def raporlar():
    from datetime import timedelta
    import json as _json
    
    # Filtreleme Parametreleri
    period = request.args.get('period', 'bu-ay')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    today = datetime.now()
    
    if period == 'bu-ay':
        start_date = today.replace(day=1)
        last_day = calendar.monthrange(today.year, today.month)[1]
        end_date = today.replace(day=last_day)
    elif period == 'gecen-ay':
        first_of_this_month = today.replace(day=1)
        last_month_end = first_of_this_month - timedelta(days=1)
        start_date = last_month_end.replace(day=1)
        end_date = last_month_end
    elif period == 'bu-yil':
        start_date = today.replace(month=1, day=1)
        end_date = today.replace(month=12, day=31)
    else:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        except:
            start_date = today.replace(day=1)
            last_day = calendar.monthrange(today.year, today.month)[1]
            end_date = today.replace(day=last_day)
            period = 'bu-ay'

    s_str = start_date.strftime('%Y-%m-%d')
    e_str = end_date.strftime('%Y-%m-%d')

    conn = database.get_db_connection()
    kasa_row = conn.execute("SELECT SUM(amount) as total FROM payments WHERE payment_date BETWEEN ? AND ?", (s_str, e_str)).fetchone()
    total_cash_out = kasa_row['total'] or 0
    
    banka_row = conn.execute("SELECT SUM(current_balance) as total FROM cards WHERE active = 1 AND current_balance < 0").fetchone()
    total_bank_debt = abs(banka_row['total'] or 0)
    
    sabit_row = conn.execute("""
        SELECT SUM(p.amount) as total 
        FROM payments p 
        JOIN bills b ON p.bill_id = b.id 
        WHERE b.is_recurring = 1 AND p.payment_date BETWEEN ? AND ?
    """, (s_str, e_str)).fetchone()
    fixed_bill_total = sabit_row['total'] or 0
    
    # Metin'in Borcu (ANLIK DURUM)
    fahri = conn.execute("SELECT id FROM users WHERE display_name = 'Fahri'").fetchone()
    metin = conn.execute("SELECT id FROM users WHERE display_name = 'Metin'").fetchone()
    metin_debt = 0
    if fahri and metin:
        dr = conn.execute("SELECT SUM(amount) as t FROM debts WHERE debtor_user_id=? AND creditor_user_id=? AND is_paid=0", (metin['id'], fahri['id'])).fetchone()
        cr = conn.execute("SELECT SUM(amount) as total FROM debt_collections").fetchone()
        metin_debt = (dr['t'] or 0) - (cr['total'] or 0)

    # 2. BÖLÜMLER İÇİN LİSTELER
    sabit_faturalar = conn.execute("""
        SELECT p.*, b.name as bill_name, b.category 
        FROM payments p 
        JOIN bills b ON p.bill_id = b.id 
        WHERE b.is_recurring = 1 AND p.payment_date BETWEEN ? AND ?
        ORDER BY p.payment_date DESC
    """, (s_str, e_str)).fetchall()
    
    ekstra_odemeler = conn.execute("""
        SELECT p.*, b.name as bill_name, b.category 
        FROM payments p 
        JOIN bills b ON p.bill_id = b.id 
        WHERE b.is_recurring = 0 AND p.payment_date BETWEEN ? AND ?
        ORDER BY p.payment_date DESC
    """, (s_str, e_str)).fetchall()
    
    kart_odemeleri = conn.execute("""
        SELECT ct.*, c.name as card_name, c.owner as card_owner
        FROM card_transactions ct
        JOIN cards c ON ct.card_id = c.id
        WHERE ct.amount > 0 AND ct.transaction_date BETWEEN ? AND ?
        ORDER BY ct.transaction_date DESC
    """, (s_str, e_str)).fetchall()

    cat_rows = conn.execute("""
        SELECT b.category, SUM(p.amount) as total 
        FROM payments p 
        JOIN bills b ON p.bill_id = b.id 
        WHERE p.payment_date BETWEEN ? AND ?
        GROUP BY b.category
    """, (s_str, e_str)).fetchall()
    
    chart_labels = [r['category'] for r in cat_rows]
    chart_data = [float(r['total']) for r in cat_rows]

    # WhatsApp Raporu Gönderimi
    if request.method == 'POST':
        period_text = "BU AY" if period == "bu-ay" else ("GEÇEN AY" if period == "gecen-ay" else ("BU YIL" if period == "bu-yil" else f"{s_str} / {e_str}"))
        msg  = f"📊 *FİNANSAL ÖZET RAPOR ({period_text})*\n"
        msg += "-----------------------------------\n\n"
        msg += f"💰 *Toplam Kasa Çıkışı:* {format_para(total_cash_out)} TL\n"
        msg += f"💳 *Banka Borcu (Anlık):* {format_para(total_bank_debt)} TL\n"
        msg += f"🏠 *Sabit Giderler:* {format_para(fixed_bill_total)} TL\n"
        debt_label = "Metin'in Borcu" if current_user.display_name == 'Fahri' else "Fahri'ye Borcum"
        msg += f"🤝 *{debt_label}:* {format_para(metin_debt)} TL\n\n"
        
        if sabit_faturalar:
            msg += "*📅 SABİT FATURALAR*\n"
            for f in sabit_faturalar:
                msg += f"• {f['bill_name']} [{f['card_used']}]: {format_para(f['amount'])} TL\n"
            msg += "\n"
            
        if ekstra_odemeler:
            msg += "*💸 EKSTRA ÖDEMELER*\n"
            for e in ekstra_odemeler:
                msg += f"• {e['bill_name']} [{e['card_used']}]: {format_para(e['amount'])} TL\n"
            msg += "\n"
            
        if kart_odemeleri:
            msg += "*💳 KART YATIRIMLARI*\n"
            for k in kart_odemeleri:
                msg += f"• {k['card_name']} ({k['card_owner']}): {format_para(k['amount'])} TL\n"
            msg += "\n"

        msg += "-----------------------------------"
        notifier.notify_all(msg)
        flash("Detaylı rapor WhatsApp üzerinden gönderildi.", "success")
        return redirect(url_for('raporlar', period=period, start_date=s_str, end_date=e_str))

    conn.close()

    return render_template_string("""{% extends 'base.html' %}
    {% block content %}
    <style>
        .filter-btn { border-radius: 10px; font-weight: 600; font-size: 0.85rem; padding: 8px 16px; border: 1px solid #e2e8f0; background: white; color: #64748b; }
        .filter-btn.active { background: var(--primary); color: white; border-color: var(--primary); }
        .stat-card { border: none; border-radius: 18px; padding: 20px; transition: transform 0.2s; }
        .stat-card:hover { transform: translateY(-3px); }
        .stat-label { font-size: 0.75rem; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 5px; }
        .stat-value { font-size: 1.6rem; font-weight: 800; color: #1e293b; }
        .mini-card { padding: 12px 15px; border-radius: 12px; }
        .section-header { font-size: 1.1rem; font-weight: 700; color: #1e293b; margin-top: 25px; margin-bottom: 15px; display: flex; align-items: center; gap: 10px; }
        .item-list-card { border-radius: 14px; overflow: hidden; border: 1px solid #f1f5f9; }
        .item-row { display: flex; justify-content: space-between; align-items: center; padding: 12px 15px; background: white; border-bottom: 1px solid #f1f5f9; }
        .item-row:last-child { border-bottom: none; }
        .item-info { display: flex; flex-direction: column; }
        .item-name { font-weight: 600; color: #334155; font-size: 0.95rem; }
        .item-meta { font-size: 0.75rem; color: #94a3b8; }
        .item-amount { font-weight: 700; color: #1e293b; font-size: 1rem; }
    </style>

    <div class="d-flex justify-content-between align-items-center mb-4">
        <h3 class="fw-bold mb-0">📊 Finansal Rapor</h3>
        <form method="POST">
            <button type="submit" class="btn btn-success fw-bold shadow-sm" style="border-radius:12px; padding: 8px 15px;">
                <span style="font-size:1.1rem;">📱</span> Raporu WhatsApp'tan Gönder
            </button>
        </form>
    </div>

    <!-- Hızlı Filtreler -->
    <div class="d-flex gap-2 mb-4 overflow-auto pb-2">
        <a href="{{ url_for('raporlar', period='bu-ay') }}" class="filter-btn text-decoration-none {{ 'active' if period == 'bu-ay' else '' }}">Bu Ay</a>
        <a href="{{ url_for('raporlar', period='gecen-ay') }}" class="filter-btn text-decoration-none {{ 'active' if period == 'gecen-ay' else '' }}">Geçen Ay</a>
        <a href="{{ url_for('raporlar', period='bu-yil') }}" class="filter-btn text-decoration-none {{ 'active' if period == 'bu-yil' else '' }}">Bu Yıl</a>
        <button class="filter-btn" data-bs-toggle="collapse" data-bs-target="#customFilter">Özel Tarih</button>
    </div>

    <div class="collapse mb-4" id="customFilter">
        <form method="GET" class="card p-3 border-0 shadow-sm" style="border-radius:15px;">
            <div class="row g-2">
                <div class="col-5"><input type="date" name="start_date" class="form-control" value="{{ start_date.strftime('%Y-%m-%d') }}"></div>
                <div class="col-5"><input type="date" name="end_date" class="form-control" value="{{ end_date.strftime('%Y-%m-%d') }}"></div>
                <div class="col-2"><button type="submit" class="btn btn-primary w-100">✓</button></div>
            </div>
            <input type="hidden" name="period" value="custom">
        </form>
    </div>

    <!-- Özet Kartları -->
    <div class="row g-3 mb-4">
        <div class="col-6">
            <div class="stat-card shadow-sm" style="background: white; border-bottom: 4px solid var(--primary);">
                <div class="stat-label">Toplam Kasa Çıkışı</div>
                <div class="stat-value">{{ total_cash_out|para }} <span style="font-size:1rem; opacity:0.6;">₺</span></div>
            </div>
        </div>
        <div class="col-6">
            <div class="stat-card shadow-sm" style="background: white; border-bottom: 4px solid var(--danger);">
                <div class="stat-label">Toplam Banka Borcu</div>
                <div class="stat-value text-danger">{{ total_bank_debt|para }} <span style="font-size:1rem; opacity:0.6;">₺</span></div>
            </div>
        </div>
        <div class="col-12">
            <div class="card p-3 shadow-sm border-0 d-flex flex-row justify-content-between align-items-center" style="background: #f8fafc; border-radius:18px;">
                <div>
                    <div class="stat-label" style="margin-bottom:0;">Sabit Fatura Toplamı</div>
                    <div style="font-size:1.3rem; font-weight:800; color:var(--primary);">{{ fixed_bill_total|para }} ₺</div>
                </div>
                <div class="text-end" style="border-left: 1px solid #e2e8f0; padding-left: 20px;">
                    <div class="stat-label" style="margin-bottom:0;">{% if current_user.display_name == 'Fahri' %}Metin'in Borcu{% else %}Fahri'ye Borcum{% endif %}</div>
                    <div style="font-size:1.1rem; font-weight:700; color:var(--danger);">{{ metin_debt|para }} ₺</div>
                </div>
            </div>
        </div>
    </div>

    <!-- Grafik Bölümü -->
    <div class="card p-4 border-0 shadow-sm mb-4" style="border-radius:20px;">
        <div class="section-header mt-0 mb-3" style="font-size:0.9rem;">📉 GİDER DAĞILIMI (Kategoriler)</div>
        <div style="max-width:250px; margin: 0 auto;">
            <canvas id="expenseChart"></canvas>
        </div>
        {% if not chart_data %}
        <div class="text-center text-muted small mt-3">Bu tarih aralığında harcama verisi yok.</div>
        {% endif %}
    </div>

    <!-- Liste Bölümleri -->
    
    <div class="section-header">🏠 Aylık Sabit Faturalar</div>
    <div class="item-list-card shadow-sm">
        {% for f in sabit_faturalar %}
        <div class="item-row">
            <div class="item-info">
                <span class="item-name">{{ f.bill_name }}</span>
                <span class="item-meta">{{ f.category }} · {{ f.card_used }} · {{ f.payment_date }}</span>
            </div>
            <div class="item-amount text-success">{{ f.amount|para }} ₺</div>
        </div>
        {% else %}
        <div class="p-4 text-center text-muted small bg-white">Ödenmiş sabit fatura bulunamadı.</div>
        {% endfor %}
    </div>

    <div class="section-header">💸 Ekstra / Manuel Ödemeler</div>
    <div class="item-list-card shadow-sm">
        {% for e in ekstra_odemeler %}
        <div class="item-row">
            <div class="item-info">
                <span class="item-name">{{ e.bill_name }}</span>
                <span class="item-meta">{{ e.category }} · {{ e.card_used }} · {{ e.payment_date }}</span>
            </div>
            <div class="item-amount" style="color:var(--primary);">{{ e.amount|para }} ₺</div>
        </div>
        {% else %}
        <div class="p-4 text-center text-muted small bg-white">Ekstra harcama kaydı yok.</div>
        {% endfor %}
    </div>

    <div class="section-header">💳 Kart Yatırımları (Ekstre)</div>
    <div class="item-list-card shadow-sm">
        {% for k in kart_odemeleri %}
        <div class="item-row">
            <div class="item-info">
                <span class="item-name">{{ k.card_name }}</span>
                <span class="item-meta">{{ k.card_owner }} · {{ k.transaction_date }}</span>
            </div>
            <div class="item-amount" style="color:var(--success);">+{{ k.amount|para }} ₺</div>
        </div>
        {% else %}
        <div class="p-4 text-center text-muted small bg-white">Kart ödeme kaydı yok.</div>
        {% endfor %}
    </div>

    {% endblock %}

    {% block scripts %}
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        const ctx = document.getElementById('expenseChart').getContext('2d');
        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: {{ chart_labels|tojson|safe }},
                datasets: [{
                    data: {{ chart_data|tojson|safe }},
                    backgroundColor: [
                        '#6366f1', '#10b981', '#f59e0b', '#ef4444', '#3b82f6', '#8b5cf6', '#ec4899', '#14b8a6'
                    ],
                    borderWidth: 2,
                    borderRadius: 5,
                    hoverOffset: 10
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            usePointStyle: true,
                            padding: 20,
                            font: { size: 11, weight: '600' }
                        }
                    }
                },
                cutout: '70%'
            }
        });
    </script>
    {% endblock %}
    """, period=period, start_date=start_date, end_date=end_date, total_cash_out=total_cash_out, total_bank_debt=total_bank_debt, fixed_bill_total=fixed_bill_total, metin_debt=metin_debt, sabit_faturalar=sabit_faturalar, ekstra_odemeler=ekstra_odemeler, kart_odemeleri=kart_odemeleri, chart_labels=chart_labels, chart_data=chart_data)

@app.route('/ayarlar', methods=['GET', 'POST'])
@login_required
def ayarlar():
    conn = database.get_db_connection()
    other_user_name = 'Metin' if current_user.display_name == 'Fahri' else 'Fahri'
    other_user = conn.execute("SELECT * FROM users WHERE display_name = ?", (other_user_name,)).fetchone()
    
    if request.method == 'POST':
        if 'test_sms' in request.form:
            try:
                notifier.notify_all("Test başarılı! Fatura Takip sistemi artık WhatsApp üzerinden çalışıyor.")
                flash("Test bildirimi arka planda tüm kullanıcılara gönderilmeye başlandı.", "success")
            except Exception as e:
                flash(f"Bildirim başlatılamadı: {e}", "danger")
        else:
            phone = request.form.get('phone')
            whatsapp_apikey = request.form.get('whatsapp_apikey', '')
            password = request.form.get('password')
            
            other_phone = request.form.get('other_phone', '')
            other_apikey = request.form.get('other_apikey', '')
            
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET phone_number = ?, whatsapp_apikey = ? WHERE id = ?", (phone, whatsapp_apikey, current_user.id))
            if other_user:
                cursor.execute("UPDATE users SET phone_number = ?, whatsapp_apikey = ? WHERE id = ?", (other_phone, other_apikey, other_user['id']))
            if password:
                cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(password, method='pbkdf2:sha256'), current_user.id))
                
            conn.commit()
            flash("Ayarlar başarıyla kaydedildi.", "success")
            return redirect(url_for('ayarlar'))
            
    conn.close()
    
    return render_template_string("""{% extends 'base.html' %}
    {% block content %}
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h3>Ayarlar</h3>
        <a href="{{ url_for('logout') }}" class="btn btn-outline-danger fw-bold">Çıkış Yap</a>
    </div>
    
    <form method="POST" class="card p-4 mb-4 shadow-sm border-0">
        <h5 class="mb-4 text-primary fw-bold border-bottom pb-2">Kendi Bilgilerin ({{ current_user.display_name }})</h5>
        <div class="mb-3">
            <label class="form-label text-secondary fw-bold">Telefon Numarası</label>
            <input type="text" name="phone" class="form-control form-control-lg" value="{{ current_user.phone_number or '' }}" placeholder="Örn: 5551234567">
        </div>
        <div class="mb-4">
            <label class="form-label text-secondary fw-bold">WhatsApp API Key (CallMeBot)</label>
            <input type="text" name="whatsapp_apikey" class="form-control form-control-lg" value="{{ current_user.whatsapp_apikey or '' }}" placeholder="Örn: 123456">
            <div class="form-text mt-1 text-muted">WhatsApp bildirimleri almak için bota mesaj atıp aldığın şifre.</div>
        </div>
        
        <h5 class="mb-4 text-primary fw-bold border-bottom pb-2 mt-2">{{ other_user_name }}'in Bilgileri</h5>
        <div class="mb-3">
            <label class="form-label text-secondary fw-bold">{{ other_user_name }}'in Telefon Numarası</label>
            <input type="text" name="other_phone" class="form-control form-control-lg" value="{{ other_user.phone_number if other_user else '' }}" placeholder="Örn: 5551234567">
        </div>
        <div class="mb-4">
            <label class="form-label text-secondary fw-bold">{{ other_user_name }}'in WhatsApp API Key'i</label>
            <input type="text" name="other_apikey" class="form-control form-control-lg" value="{{ other_user.whatsapp_apikey if other_user else '' }}" placeholder="Örn: 123456">
        </div>
        
        <h5 class="mb-4 text-primary fw-bold border-bottom pb-2 mt-2">Güvenlik</h5>
        <div class="mb-4">
            <label class="form-label text-secondary fw-bold">Yeni Şifre</label>
            <input type="password" name="password" class="form-control form-control-lg" placeholder="Sadece kendi şifreni değiştirmek istiyorsan doldur">
        </div>
        <button type="submit" class="btn btn-primary btn-lg w-100 py-3 fw-bold shadow">Tüm Ayarları Kaydet</button>
    </form>
    
    <form method="POST" class="card p-4 shadow-sm border-0 bg-light">
        <h5 class="mb-3 text-secondary fw-bold">Bağlantı Testi</h5>
        <p class="text-muted small">Bu butona basarak CallMeBot üzerinden WhatsApp'ınıza test mesajı gönderebilirsiniz.</p>
        <input type="hidden" name="test_sms" value="1">
        <button type="submit" class="btn btn-outline-success btn-lg w-100 py-3 fw-bold">Sistemi Test Et (WhatsApp Gönder)</button>
    </form>
    {% endblock %}
    """, other_user=other_user, other_user_name=other_user_name)

@app.route('/kartlar', methods=['GET', 'POST'])
@login_required
def kartlar():
    conn = database.get_db_connection()
    if request.method == 'POST':
        if 'delete_id' in request.form:
            conn.execute("UPDATE cards SET active = 0 WHERE id = ?", (request.form.get('delete_id'),))
            flash("Kart silindi.", "success")
        else:
            name = request.form.get('name', '').strip()
            owner = request.form.get('owner', 'Fahri')
            card_type = request.form.get('type')
            due_day = request.form.get('due_day')
            due_day = int(due_day) if due_day else None
            current_balance = float(request.form.get('current_balance') or 0)
            total_limit = float(request.form.get('total_limit') or 0)
            statement_day = int(request.form.get('statement_day') or 1)

            if not name:
                flash("Kart adı boş olamaz.", "danger")
            else:
                conn.execute('''
                    INSERT INTO cards (name, owner, type, due_day, current_balance, total_limit, statement_day, active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                ''', (name, owner, card_type, due_day, current_balance, total_limit, statement_day))
                flash("Kart/Eksi Hesap başarıyla eklendi.", "success")
        conn.commit()
        return redirect(url_for('kartlar'))
        
    cards = conn.execute("SELECT * FROM cards WHERE active = 1 ORDER BY type DESC, name ASC").fetchall()
    cards_list = [dict(c) for c in cards]
    conn.close()
    
    total_cc_debt = sum(c['current_balance'] for c in cards_list if c['type'] == 'Kredi Kartı' and c['current_balance'] < 0)
    total_eh_debt = sum(c['current_balance'] for c in cards_list if c['type'] == 'Eksi Hesap' and c['current_balance'] < 0)
    total_debt = total_cc_debt + total_eh_debt

    cc_cards = [c for c in cards_list if c['type'] == 'Kredi Kartı']
    eh_cards = [c for c in cards_list if c['type'] == 'Eksi Hesap']

    return render_template_string("""{% extends 'base.html' %}
    {% block content %}
    <div class="d-flex justify-content-between align-items-center mb-4">
        <span class="page-title">💳 Kartlar & Eksi Hesaplar</span>
        <button class="btn btn-primary px-4 fw-bold shadow-sm" data-bs-toggle="modal" data-bs-target="#addCardModal">+ Ekle</button>
    </div>

    <div class="card p-3 shadow-sm border-0 mb-4" style="background: linear-gradient(135deg, #334155 0%, #0f172a 100%); color: white;">
        <div class="row text-center">
            <div class="col-4 border-end border-secondary">
                <div class="small opacity-75 fw-bold" style="font-size:0.65rem; text-transform:uppercase;">Kart Borcu</div>
                <div class="fw-bold" style="font-size:1.1rem; color:#fca5a5;">{{ total_cc_debt|para }} ₺</div>
            </div>
            <div class="col-4 border-end border-secondary">
                <div class="small opacity-75 fw-bold" style="font-size:0.65rem; text-transform:uppercase;">Eksi Hesap</div>
                <div class="fw-bold" style="font-size:1.1rem; color:#fca5a5;">{{ total_eh_debt|para }} ₺</div>
            </div>
            <div class="col-4">
                <div class="small opacity-75 fw-bold" style="font-size:0.65rem; text-transform:uppercase;">Toplam Borç</div>
                <div class="fw-bold" style="font-size:1.1rem; color:#f87171;">{{ total_debt|para }} ₺</div>
            </div>
        </div>
    </div>
    
    <div class="section-title">Kredi Kartları</div>
    <div class="row g-2 mb-4">
        {% for c in cc_cards %}
        <div class="col-12">
            <a href="{{ url_for('kart_detay', card_id=c.id) }}" class="text-decoration-none">
                <div class="card p-3 shadow-sm mb-0">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <div class="fw-bold" style="color:var(--text);">{{ c.name }}</div>
                            <div class="small text-muted">{{ c.owner }} · Son Ödeme: {{ c.due_day }} | Kesim: {{ c.statement_day }}</div>
                        </div>
                        <div class="text-end">
                            <div style="font-weight:700; font-size:1.2rem; color:{% if c.current_balance < 0 %}var(--danger){% else %}var(--success){% endif %};">
                                {{ c.current_balance|para }} ₺
                            </div>
                        </div>
                    </div>
                    {% if c.total_limit > 0 %}
                    <div class="mt-2">
                        {% set used_percent = ((c.current_balance|abs) / c.total_limit * 100)|int %}
                        {% set available = c.total_limit + c.current_balance %}
                        <div class="d-flex justify-content-between small text-muted mb-1">
                            <span>Kullanım: %{{ used_percent }}</span>
                            <span>Limit: {{ c.total_limit|para }} ₺</span>
                        </div>
                        <div class="progress" style="height: 8px; border-radius: 4px; background-color: #e2e8f0;">
                            <div class="progress-bar {% if used_percent > 85 %}bg-danger{% elif used_percent > 60 %}bg-warning{% else %}bg-primary{% endif %}" 
                                 role="progressbar" style="width: {{ used_percent }}%;" aria-valuenow="{{ used_percent }}" aria-valuemin="0" aria-valuemax="100"></div>
                        </div>
                        <div class="text-end small fw-bold mt-1" style="color:var(--success);">Kullanılabilir: {{ available|para }} ₺</div>
                    </div>
                    {% endif %}
                </div>
            </a>
        </div>
        {% else %}
        <div class="col-12"><div class="card p-3 text-center text-muted small">Henüz kredi kartı eklenmemiş.</div></div>
        {% endfor %}
    </div>

    <div class="section-title">Eksi Hesaplar / KMH</div>
    <div class="row g-2 mb-4">
        {% for c in eh_cards %}
        <div class="col-12">
            <a href="{{ url_for('kart_detay', card_id=c.id) }}" class="text-decoration-none">
                <div class="card p-3 shadow-sm mb-0">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <div class="fw-bold" style="color:var(--text);">{{ c.name }}</div>
                            <div class="small text-muted">{{ c.owner }}</div>
                        </div>
                        <div class="text-end">
                            <div style="font-weight:700; font-size:1.2rem; color:{% if c.current_balance < 0 %}var(--danger){% else %}var(--success){% endif %};">
                                {{ c.current_balance|para }} ₺
                            </div>
                        </div>
                    </div>
                </div>
            </a>
        </div>
        {% else %}
        <div class="col-12"><div class="card p-3 text-center text-muted small">Henüz eksi hesap eklenmemiş.</div></div>
        {% endfor %}
    </div>

    <!-- Ekle Modal -->
    <div class="modal fade" id="addCardModal" tabindex="-1">
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <form method="POST">
              <div class="modal-header border-0 pb-0">
                <h5 class="modal-title fw-bold">Yeni Kart / Hesap Ekle</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
              </div>
              <div class="modal-body">
                <div class="mb-3">
                    <label class="form-label text-secondary small fw-bold">Hesap/Kart Adı</label>
                    <input type="text" name="name" class="form-control" placeholder="Örn: Ziraat Kredi Kartı" required>
                </div>
                <div class="mb-3">
                    <label class="form-label text-secondary small fw-bold">Sahibi</label>
                    <select name="owner" class="form-select">
                        <option value="Fahri">Fahri</option>
                        <option value="Metin">Metin</option>
                        <option value="Şirket/Ortak">Şirket/Ortak</option>
                    </select>
                </div>
                <div class="mb-3">
                    <label class="form-label text-secondary small fw-bold">Tür</label>
                    <div class="d-flex gap-2">
                        <input type="radio" class="btn-check" name="type" id="type_cc" value="Kredi Kartı" checked>
                        <label class="btn btn-outline-primary flex-fill" for="type_cc">Kredi Kartı</label>
                        <input type="radio" class="btn-check" name="type" id="type_eh" value="Eksi Hesap">
                        <label class="btn btn-outline-primary flex-fill" for="type_eh">Eksi Hesap</label>
                    </div>
                </div>
                <div class="row">
                    <div class="col-6 mb-3">
                        <label class="form-label text-secondary small fw-bold">Toplam Limit</label>
                        <input type="number" step="0.01" name="total_limit" class="form-control" placeholder="10000" required>
                    </div>
                    <div class="col-6 mb-3">
                        <label class="form-label text-secondary small fw-bold">Güncel Bakiye</label>
                        <input type="number" step="0.01" name="current_balance" class="form-control" value="0">
                    </div>
                </div>
                <div class="row" id="cc_days_container">
                    <div class="col-6 mb-3">
                        <label class="form-label text-secondary small fw-bold">Kesim Günü</label>
                        <input type="number" name="statement_day" class="form-control" placeholder="1-31" min="1" max="31" value="1">
                    </div>
                    <div class="col-6 mb-3">
                        <label class="form-label text-secondary small fw-bold">Son Ödeme Günü</label>
                        <input type="number" name="due_day" class="form-control" placeholder="1-31" min="1" max="31">
                    </div>
                </div>
              </div>
              <div class="modal-footer border-0 pt-0">
                <button type="submit" class="btn btn-primary w-100 py-3 fw-bold shadow">Kaydet</button>
              </div>
          </form>
        </div>
      </div>
    </div>

    <script>
        document.querySelectorAll('input[name="type"]').forEach(radio => {
            radio.addEventListener('change', function() {
                const ccDaysContainer = document.getElementById('cc_days_container');
                if (this.value === 'Eksi Hesap') {
                    ccDaysContainer.style.display = 'none';
                } else {
                    ccDaysContainer.style.display = 'flex';
                }
            });
        });
    </script>
    {% endblock %}
    """, cc_cards=cc_cards, eh_cards=eh_cards, total_cc_debt=total_cc_debt, total_eh_debt=total_eh_debt, total_debt=total_debt)

@app.route('/kart/<int:card_id>', methods=['GET', 'POST'])
@login_required
def kart_detay(card_id):
    conn = database.get_db_connection()
    if request.method == 'POST' and 'edit_card' in request.form:
        name = request.form.get('name', '').strip()
        owner = request.form.get('owner')
        total_limit = float(request.form.get('total_limit') or 0)
        statement_day = int(request.form.get('statement_day') or 1)
        due_day = request.form.get('due_day')
        due_day = int(due_day) if due_day else None
        
        conn.execute('''
            UPDATE cards 
            SET name=?, owner=?, total_limit=?, statement_day=?, due_day=?
            WHERE id=?
        ''', (name, owner, total_limit, statement_day, due_day, card_id))
        conn.commit()
        flash("Kart bilgileri güncellendi.", "success")
        return redirect(url_for('kart_detay', card_id=card_id))

    card = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
    if not card:
        conn.close()
        flash("Kart bulunamadı.", "danger")
        return redirect(url_for('kartlar'))
    
    transactions = conn.execute("SELECT * FROM card_transactions WHERE card_id = ? ORDER BY transaction_date DESC, id DESC", (card_id,)).fetchall()
    conn.close()
    
    return render_template_string("""{% extends 'base.html' %}
    {% block content %}
    <div class="d-flex justify-content-between align-items-center mb-3">
        <a href="{{ url_for('kartlar') }}" class="btn btn-sm btn-outline-secondary">← Geri</a>
        <div class="d-flex gap-2">
            <button class="btn btn-sm btn-outline-primary" data-bs-toggle="modal" data-bs-target="#editCardModal">Düzenle</button>
            <form method="POST" action="{{ url_for('kart_sil', card_id=card.id) }}" onsubmit="return confirm('Bu kartı ve tüm geçmişini silmek istediğinize emin misiniz?');" style="margin:0;">
                <button class="btn btn-sm btn-outline-danger">Sil</button>
            </form>
        </div>
    </div>

    <div class="card p-4 text-center shadow-sm mb-4 border-0" style="background: linear-gradient(135deg, #1e293b 0%, #334155 100%); color: white;">
        <div class="small opacity-75 text-uppercase fw-bold mb-1">{{ card.name }} ({{ card.owner }})</div>
        <div style="font-size: 2.4rem; font-weight: 700;" class="mb-1">{{ card.current_balance|para }} ₺</div>
        <div class="small opacity-75">
            {% if card.type == 'Kredi Kartı' %}
                Kesim: {{ card.statement_day }} | Son Ödeme: {{ card.due_day }}
            {% else %}
                Eksi Hesap / KMH
            {% endif %}
        </div>
        
        {% if card.type == 'Kredi Kartı' and card.total_limit > 0 %}
        <div class="mt-3 px-4">
            {% set used_percent = ((card.current_balance|abs) / card.total_limit * 100)|int %}
            <div class="progress" style="height: 10px; border-radius: 5px; background-color: rgba(255,255,255,0.2);">
                <div class="progress-bar {% if used_percent > 85 %}bg-danger{% elif used_percent > 60 %}bg-warning{% else %}bg-info{% endif %}" 
                     role="progressbar" style="width: {{ used_percent }}%;"></div>
            </div>
            <div class="d-flex justify-content-between small mt-1">
                <span>Doluluk: %{{ used_percent }}</span>
                <span>Limit: {{ card.total_limit|para }} ₺</span>
            </div>
        </div>
        {% endif %}

        <button class="btn btn-primary mt-4 py-2 px-4 fw-bold shadow" data-bs-toggle="modal" data-bs-target="#addTransactionModal">
            💳 İşlem Ekle
        </button>
    </div>

    <div class="section-title">İşlem Geçmişi</div>
    <div class="list-group shadow-sm" style="border-radius:14px;overflow:hidden;">
        {% for t in transactions %}
        <div class="list-group-item d-flex justify-content-between align-items-center">
            <div>
                <div style="font-weight:600; font-size:0.95rem;">{{ t.note or 'İşlem' }}</div>
                <div style="font-size:0.8rem; color:var(--text-muted);">{{ t.transaction_date }}</div>
            </div>
            <div class="d-flex align-items-center gap-3">
                <div style="font-weight:700; color:{% if t.amount > 0 %}var(--success){% else %}var(--danger){% endif %};">
                    {{ t.amount|para }} ₺
                </div>
                <form method="POST" action="{{ url_for('kart_islem_sil', transaction_id=t.id) }}" onsubmit="return confirm('Bu işlemi silmek istediğinize emin misiniz?');">
                    <button class="btn btn-sm" style="background:#fee2e2;color:#991b1b;border:none;border-radius:8px;padding:4px 8px;">✕</button>
                </form>
            </div>
        </div>
        {% else %}
        <div class="list-group-item text-center text-muted py-4 small">Henüz işlem kaydı yok.</div>
        {% endfor %}
    </div>

    <!-- Düzenle Modal -->
    <div class="modal fade" id="editCardModal" tabindex="-1">
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <form method="POST">
              <input type="hidden" name="edit_card" value="1">
              <div class="modal-header border-0">
                <h5 class="modal-title fw-bold">Kart Bilgilerini Güncelle</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
              </div>
              <div class="modal-body">
                <div class="mb-3">
                    <label class="form-label small fw-bold">Kart Adı</label>
                    <input type="text" name="name" class="form-control" value="{{ card.name }}" required>
                </div>
                <div class="mb-3">
                    <label class="form-label small fw-bold">Sahibi</label>
                    <select name="owner" class="form-select">
                        <option value="Fahri" {% if card.owner == 'Fahri' %}selected{% endif %}>Fahri</option>
                        <option value="Metin" {% if card.owner == 'Metin' %}selected{% endif %}>Metin</option>
                        <option value="Şirket/Ortak" {% if card.owner == 'Şirket/Ortak' %}selected{% endif %}>Şirket/Ortak</option>
                    </select>
                </div>
                <div class="mb-3">
                    <label class="form-label small fw-bold">Toplam Limit</label>
                    <input type="number" step="0.01" name="total_limit" class="form-control" value="{{ card.total_limit }}" required>
                </div>
                {% if card.type == 'Kredi Kartı' %}
                <div class="row">
                    <div class="col-6 mb-3">
                        <label class="form-label small fw-bold">Kesim Günü</label>
                        <input type="number" name="statement_day" class="form-control" value="{{ card.statement_day }}" min="1" max="31">
                    </div>
                    <div class="col-6 mb-3">
                        <label class="form-label small fw-bold">Son Ödeme Günü</label>
                        <input type="number" name="due_day" class="form-control" value="{{ card.due_day }}" min="1" max="31">
                    </div>
                </div>
                {% endif %}
              </div>
              <div class="modal-footer border-0">
                <button type="submit" class="btn btn-primary w-100 py-3 fw-bold">Kaydet</button>
              </div>
          </form>
        </div>
      </div>
    </div>

    <!-- İşlem Ekle Modal -->
    <div class="modal fade" id="addTransactionModal" tabindex="-1">
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <form method="POST" action="{{ url_for('kart_islem_ekle', card_id=card.id) }}">
              <div class="modal-header border-0 pb-0">
                <h5 class="modal-title fw-bold">İşlem Ekle</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
              </div>
              <div class="modal-body">
                <div class="mb-3">
                    <label class="form-label text-secondary small fw-bold">Tutar (+ veya -)</label>
                    <input type="number" step="0.01" name="amount" class="form-control form-control-lg" placeholder="Örn: 5000 veya -2500" required>
                </div>
                <div class="mb-3">
                    <label class="form-label text-secondary small fw-bold">İşlem Tarihi</label>
                    <input type="date" name="transaction_date" class="form-control" value="{{ now_str }}" required>
                </div>
                <div class="mb-3">
                    <label class="form-label text-secondary small fw-bold">Not</label>
                    <input type="text" name="note" class="form-control" placeholder="Örn: Market harcaması">
                </div>
              </div>
              <div class="modal-footer border-0 pt-0">
                <button type="submit" class="btn btn-primary w-100 py-3 fw-bold">Kaydet</button>
              </div>
          </form>
        </div>
      </div>
    </div>
    {% endblock %}
    """, card=card, transactions=transactions, now_str=datetime.now().strftime('%Y-%m-%d'))

@app.route('/kart/<int:card_id>/islem', methods=['POST'])
@login_required
def kart_islem_ekle(card_id):
    amount = float(request.form.get('amount') or 0)
    transaction_date = request.form.get('transaction_date')
    note = request.form.get('note', '')
    
    conn = database.get_db_connection()
    # İşlemi kaydet
    conn.execute("INSERT INTO card_transactions (card_id, amount, transaction_date, note) VALUES (?, ?, ?, ?)",
                 (card_id, amount, transaction_date, note))
    # Bakiyeyi güncelle
    conn.execute("UPDATE cards SET current_balance = current_balance + ? WHERE id = ?", (amount, card_id))
    conn.commit()
    conn.close()
    flash("İşlem başarıyla eklendi.", "success")
    return redirect(url_for('kart_detay', card_id=card_id))

@app.route('/kart/islem_sil/<int:transaction_id>', methods=['POST'])
@login_required
def kart_islem_sil(transaction_id):
    conn = database.get_db_connection()
    t = conn.execute("SELECT * FROM card_transactions WHERE id = ?", (transaction_id,)).fetchone()
    if t:
        card_id = t['card_id']
        amount = t['amount']
        # Bakiyeyi geri al
        conn.execute("UPDATE cards SET current_balance = current_balance - ? WHERE id = ?", (amount, card_id))
        # İşlemi sil
        conn.execute("DELETE FROM card_transactions WHERE id = ?", (transaction_id,))
        conn.commit()
        flash("İşlem silindi ve bakiye geri alındı.", "success")
        conn.close()
        return redirect(url_for('kart_detay', card_id=card_id))
    conn.close()
    return redirect(url_for('kartlar'))

@app.route('/kart_sil/<int:card_id>', methods=['POST'])
@login_required
def kart_sil(card_id):
    conn = database.get_db_connection()
    conn.execute("UPDATE cards SET active = 0 WHERE id = ?", (card_id,))
    conn.commit()
    conn.close()
    flash("Kart silindi.", "success")
    return redirect(url_for('kartlar'))

@app.errorhandler(500)
def internal_error(e):
    import traceback
    err = traceback.format_exc()
    print(f"[500 HATA]:\n{err}")
    return f"""
    <div style='font-family:monospace;padding:20px;background:#fff3cd;border:2px solid #ffc107;border-radius:8px;margin:20px;'>
        <h2>⚠️ Geçici Bir Sorun Oluştu</h2>
        <p>Lütfen bu hatayı Fahri'ye iletin:</p>
        <pre style='background:#f8f9fa;padding:10px;border-radius:6px;overflow:auto;'>{err}</pre>
        <a href='/' style='background:#6366f1;color:white;padding:10px 20px;border-radius:8px;text-decoration:none;'>Ana Sayfaya Dön</a>
    </div>
    """, 500

@app.route('/cron')
def cron_job():
    try:
        check_bills_and_notify()
    except Exception as e:
        print(f"[Cron Hata]: {e}")
    return "Cron run successfully", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5002)))
