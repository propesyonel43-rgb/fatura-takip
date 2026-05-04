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
        
        m_phone = request.form.get('metin_phone')
        
        conn.execute("INSERT INTO users (username, password_hash, display_name, phone_number) VALUES (?, ?, ?, ?)",
                     (f_user, generate_password_hash(f_pass, method='pbkdf2:sha256'), "Fahri", f_phone))
        # We still insert Metin as a hidden user just for phone number and debt tracking, but he won't log in.
        conn.execute("INSERT INTO users (username, password_hash, display_name, phone_number) VALUES (?, ?, ?, ?)",
                     ("metin_hidden", generate_password_hash("hidden", method='pbkdf2:sha256'), "Metin", m_phone))
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
    
    bills = conn.execute("SELECT * FROM bills WHERE active = 1").fetchall()
    
    fahri = conn.execute("SELECT id FROM users WHERE display_name = 'Fahri'").fetchone()
    metin = conn.execute("SELECT id FROM users WHERE display_name = 'Metin'").fetchone()
    
    metin_debt = 0
    if fahri and metin:
        debt_row = conn.execute("SELECT SUM(amount) as total FROM debts WHERE debtor_user_id = ? AND creditor_user_id = ? AND is_paid = 0", (metin['id'], fahri['id'])).fetchone()
        metin_debt = debt_row['total'] or 0
        
    payments = conn.execute('''
        SELECT p.*, b.name as bill_name, u.display_name as payer_name 
        FROM payments p 
        JOIN bills b ON p.bill_id = b.id 
        JOIN users u ON p.paid_by_user_id = u.id 
        ORDER BY p.payment_date DESC LIMIT 5
    ''').fetchall()
    
    dashboard_bills = []
    today_day = today.day
    for b in bills:
        cycle = conn.execute("SELECT status FROM monthly_cycles WHERE bill_id = ? AND year = ? AND month = ?", (b['id'], today.year, today.month)).fetchone()
        status_color = ""
        days_left = b['due_day'] - today_day
        if cycle and cycle['status'] == 'odendi':
            status_color = "success"
        elif days_left < 0 or days_left == 0:
            status_color = "danger"
        elif days_left <= 7:
            status_color = "warning"
        else:
            status_color = "light"
            
        dashboard_bills.append({
            'name': b['name'],
            'amount': b['amount'],
            'color': status_color,
            'days_left': days_left,
            'is_autopay': b['is_autopay']
        })
        
    conn.close()
    return render_template_string("""{% extends 'base.html' %}
    {% block content %}
    <div class="d-flex justify-content-between align-items-center mb-4">
        <span class="page-title">👋 Merhaba, {{ current_user.display_name }}</span>
        <a href="{{ url_for('ayarlar') }}" class="btn btn-sm" style="background:#f1f5f9;border-radius:10px;font-size:0.85rem;">⚙️ Ayarlar</a>
    </div>

    <div class="hero-card mb-4">
        <div class="label">Metin'in Toplam Borcu</div>
        <div class="amount">{{ '%.2f'|format(metin_debt) }} ₺</div>
        <div style="font-size:0.8rem;opacity:0.75;margin-top:6px;">Güncel bakiye</div>
    </div>

    <div class="section-title">Bu Ay Faturalar</div>
    <div class="row g-2 mb-4">
        {% for b in dashboard_bills %}
        <div class="col-6">
            <div class="bill-chip chip-{{ b.color }} position-relative">
                {% if b.is_autopay %}<span class="badge" style="background:#6366f1;font-size:0.65rem;position:absolute;top:8px;right:8px;">OTO</span>{% endif %}
                <div style="font-weight:600;font-size:0.9rem;">{{ b.name }}</div>
                <div style="font-size:1.1rem;font-weight:700;">{{ b.amount }} ₺</div>
                {% if b.color == 'success' %}<div style="font-size:0.72rem;">✓ Ödendi</div>
                {% elif b.color == 'danger' %}<div style="font-size:0.72rem;">⚠ Geçti</div>
                {% elif b.color == 'warning' %}<div style="font-size:0.72rem;">⏰ {{ b.days_left }} gün kaldı</div>
                {% else %}<div style="font-size:0.72rem;">{{ b.days_left }} gün</div>{% endif %}
            </div>
        </div>
        {% else %}
        <div class="col-12"><div class="card p-4 text-center text-muted">Henüz fatura eklenmemiş.</div></div>
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
                    <div style="font-weight:700;color:var(--success);">{{ p.amount }} ₺</div>
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
    """, metin_debt=metin_debt, dashboard_bills=dashboard_bills, payments=payments)

@app.route('/faturalar', methods=['GET', 'POST'])
@login_required
def faturalar():
    conn = database.get_db_connection()
    if request.method == 'POST':
        if 'delete_id' in request.form:
            conn.execute("UPDATE bills SET active = 0 WHERE id = ?", (request.form.get('delete_id'),))
            flash("Fatura silindi.", "success")
        else:
            name = request.form.get('name')
            amount = float(request.form.get('amount') or 0)
            due_day = int(request.form.get('due_day'))
            last_payment_day = int(request.form.get('last_payment_day'))
            category = request.form.get('category')
            subscriber_no = request.form.get('subscriber_no', '')
            is_recurring = 1 if request.form.get('is_recurring') == 'on' else 0
            is_autopay = 1 if request.form.get('is_autopay') == 'on' else 0

            conn.execute('''
                INSERT INTO bills (name, owner, amount, due_day, last_payment_day, category, is_recurring, is_autopay, subscriber_no)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (name, "Ortak", amount, due_day, last_payment_day, category, is_recurring, is_autopay, subscriber_no))
            flash("Fatura başarıyla eklendi.", "success")
        conn.commit()
        return redirect(url_for('faturalar'))
        
    bills = conn.execute("SELECT * FROM bills WHERE active = 1 ORDER BY id DESC").fetchall()
    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
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
    
    {% for b in bills %}
    <div class="card p-3 shadow-sm mb-3">
        <div class="d-flex justify-content-between align-items-start">
            <div>
                <h5 class="mb-0">{{ b.name }}</h5>
                {% if b.subscriber_no %}<div style="font-size:0.78rem;color:var(--text-muted);">Abone No: <strong>{{ b.subscriber_no }}</strong></div>{% endif %}
                <div class="mt-1">
                    <span class="badge bg-secondary">{{ b.category }}</span>
                    {% if b.is_autopay %}<span class="badge" style="background:#6366f1;">Otomatik</span>{% endif %}
                    {% if b.is_recurring %}<span class="badge bg-light text-muted">Tekrarlı</span>{% endif %}
                </div>
            </div>
            <form method="POST" class="d-inline" onsubmit="return confirm('Bu faturasını silmek istediğinize emin misiniz?');">
                <input type="hidden" name="delete_id" value="{{ b.id }}">
                <button class="btn btn-sm" style="background:#fee2e2;color:#991b1b;border:none;border-radius:8px;">Sil</button>
            </form>
        </div>
        <div class="d-flex justify-content-between align-items-end mt-3" style="background:#f8fafc;border-radius:10px;padding:10px 12px;">
            <div class="small">
                <div>Ödeme Günü: <strong>Ayın {{ b.due_day }}. günü</strong></div>
                <div>Son Gün: <strong style="color:var(--danger);">Ayın {{ b.last_payment_day }}. günü</strong></div>
            </div>
            <div style="font-weight:700;font-size:1.4rem;color:var(--primary);">{{ b.amount }} ₺</div>
        </div>
    </div>
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
                  <input class="form-check-input" type="checkbox" name="is_autopay" id="is_autopay">
                  <label class="form-check-label text-danger" for="is_autopay">Otomatik Ödemede</label>
                </div>
              </div>
              <div class="modal-footer border-0 pt-0 mt-3">
                <button type="submit" class="btn btn-primary w-100 py-3 fs-5 fw-bold shadow">Kaydet</button>
              </div>
          </form>
        </div>
      </div>
    </div>
    {% endblock %}
    """, bills=bills, categories=categories)

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
            <form method="POST" onsubmit="return confirm('Silmek istediğinize emin misiniz?');">
                <input type="hidden" name="delete_id" value="{{ cat.id }}">
                <button class="btn btn-sm btn-outline-danger">Sil</button>
            </form>
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
        paid_by_display = request.form.get('paid_by')
        card_used = request.form.get('card_used')
        payment_date = request.form.get('payment_date')
        notes = request.form.get('notes', '')
        
        payer = dict(conn.execute("SELECT * FROM users WHERE display_name = ?", (paid_by_display,)).fetchone())
        bill = dict(conn.execute("SELECT * FROM bills WHERE id = ?", (bill_id,)).fetchone())
        
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO payments (bill_id, paid_by_user_id, paid_for_owner, amount, card_used, payment_date, is_on_behalf, notes)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        ''', (bill_id, payer['id'], "Ortak", amount, card_used, payment_date, notes))
        payment_id = cursor.lastrowid
        
        debt_amount = amount
        
        metin = conn.execute("SELECT * FROM users WHERE display_name = 'Metin'").fetchone()
        fahri = conn.execute("SELECT * FROM users WHERE display_name = 'Fahri'").fetchone()
        
        if paid_by_display == 'Fahri' and metin:
            cursor.execute('''
                INSERT INTO debts (payment_id, debtor_user_id, creditor_user_id, amount, is_paid)
                VALUES (?, ?, ?, ?, 0)
            ''', (payment_id, metin['id'], payer['id'], amount))
            debt_amount = amount
        elif paid_by_display == 'Metin' and fahri:
            cursor.execute('''
                INSERT INTO debts (payment_id, debtor_user_id, creditor_user_id, amount, is_paid)
                VALUES (?, ?, ?, ?, 0)
            ''', (payment_id, fahri['id'], payer['id'], amount))
            debt_amount = amount
                
        dt = datetime.strptime(payment_date, '%Y-%m-%d')
        existing_cycle = conn.execute("SELECT id FROM monthly_cycles WHERE bill_id = ? AND year = ? AND month = ?",
                                     (bill_id, dt.year, dt.month)).fetchone()
        if existing_cycle:
            conn.execute("UPDATE monthly_cycles SET status = 'odendi', payment_id = ? WHERE bill_id = ? AND year = ? AND month = ?",
                         (payment_id, bill_id, dt.year, dt.month))
        else:
            conn.execute("INSERT INTO monthly_cycles (bill_id, year, month, status, payment_id) VALUES (?, ?, ?, 'odendi', ?)",
                         (bill_id, dt.year, dt.month, payment_id))
        
        conn.commit()
        
        msg = f"✅ {paid_by_display} odedi: {bill['name']} - {amount}TL ({card_used})"
        if debt_amount > 0 and metin and fahri:
            if paid_by_display == 'Fahri':
                total_debt_row = conn.execute("SELECT SUM(amount) as t FROM debts WHERE debtor_user_id = ? AND creditor_user_id = ? AND is_paid = 0", (metin['id'], fahri['id'])).fetchone()
                total_debt = total_debt_row['t'] or 0
                msg += f"\n💸 Yeni borc: +{amount}TL | Metin'in Toplam Borcu: {total_debt}TL"
            
        notifier.notify_all(msg)
        
        flash("Ödeme başarıyla kaydedildi ve SMS gönderildi.", "success")
        return redirect(url_for('odeme_kaydet'))
        
    bills = conn.execute("SELECT * FROM bills WHERE active = 1").fetchall()
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
                <option value="{{ b.id }}" data-amount="{{ b.amount }}">{{ b.name }}</option>
                {% endfor %}
            </select>
        </div>
        <div class="mb-4">
            <label class="form-label fw-bold text-secondary">Tutar (TL)</label>
            <div class="input-group input-group-lg">
                <span class="input-group-text">₺</span>
                <input type="number" step="0.01" name="amount" id="amount" class="form-control" required>
            </div>
        </div>
        <div class="mb-4">
            <label class="form-label fw-bold text-secondary">Kim Ödedi?</label>
            <div class="d-flex gap-2">
                <input type="radio" class="btn-check btn-check-custom" name="paid_by" id="pb_fahri" value="Fahri" required>
                <label class="btn btn-outline-primary flex-fill" for="pb_fahri">Fahri</label>

                <input type="radio" class="btn-check btn-check-custom" name="paid_by" id="pb_metin" value="Metin" required>
                <label class="btn btn-outline-primary flex-fill" for="pb_metin">Metin</label>
            </div>
            <div class="form-text mt-2 text-danger">Seçilen kişi karşı tarafa otomatik borç yazdıracaktır.</div>
        </div>
        <div class="mb-4">
            <label class="form-label fw-bold text-secondary">Hangi Kart Kullanıldı?</label>
            <div class="row g-2">
                <div class="col-4">
                    <input type="radio" class="btn-check btn-check-custom" name="card_used" id="card_fahri" value="Fahri Kartı" required>
                    <label class="btn btn-outline-secondary w-100" for="card_fahri">Fahri</label>
                </div>
                <div class="col-4">
                    <input type="radio" class="btn-check btn-check-custom" name="card_used" id="card_metin" value="Metin Kartı" required>
                    <label class="btn btn-outline-secondary w-100" for="card_metin">Metin</label>
                </div>
                <div class="col-4">
                    <input type="radio" class="btn-check btn-check-custom" name="card_used" id="card_sirket" value="Şirket Kartı" required>
                    <label class="btn btn-outline-secondary w-100" for="card_sirket">Şirket</label>
                </div>
            </div>
        </div>
        
        <div class="mb-4">
            <label class="form-label fw-bold text-secondary">Ödeme Tarihi</label>
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
    </script>
    {% endblock %}
    """, bills=bills)

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
        SELECT d.*, p.payment_date, b.name as bill_name 
        FROM debts d
        JOIN payments p ON d.payment_id = p.id
        JOIN bills b ON p.bill_id = b.id
        WHERE d.debtor_user_id = ? AND d.creditor_user_id = ? AND d.is_paid = 0
        ORDER BY p.payment_date DESC
    ''', (metin['id'], fahri['id'])).fetchall()
    
    total_row = conn.execute("SELECT SUM(amount) as t FROM debts WHERE debtor_user_id = ? AND creditor_user_id = ? AND is_paid = 0", (metin['id'], fahri['id'])).fetchone()
    total = total_row['t'] or 0
    
    conn.close()
    
    return render_template_string("""{% extends 'base.html' %}
    {% block content %}
    <h3 class="mb-4">Borç Takibi</h3>
    <div class="card p-4 mb-4 text-center bg-danger text-white shadow-lg border-0" style="background: linear-gradient(135deg, #dc3545, #b02a37);">
        <h5 class="opacity-75">Metin'in Toplam Borcu</h5>
        <div class="dashboard-debt" style="font-size: 3.5rem;">{{ total }} TL</div>
    </div>
    
    <h5 class="text-secondary mb-3">Bekleyen Borç Kalemleri</h5>
    <div class="list-group shadow-sm">
        {% for d in debts %}
        <div class="list-group-item list-group-item-action d-flex justify-content-between align-items-center p-3 border-start border-4 border-danger">
            <div>
                <h5 class="mb-1 fw-bold">{{ d.bill_name }}</h5>
                <small class="text-muted d-block mb-1">Ödeme Tarihi: {{ d.payment_date }}</small>
                <div class="fw-bold fs-5 text-danger">{{ d.amount }} TL</div>
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
                                <div>{{ item.amount }}</div>
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
    year = int(request.args.get('year', datetime.now().year))
    month = int(request.args.get('month', datetime.now().month))
    month_names = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

    conn = database.get_db_connection()
    start_date = f"{year}-{month:02d}-01"
    end_date   = f"{year}-{month:02d}-31"

    payments = conn.execute("""
        SELECT p.*, b.category, b.name as bill_name
        FROM payments p JOIN bills b ON p.bill_id = b.id
        WHERE p.payment_date >= ? AND p.payment_date <= ?
    """, (start_date, end_date)).fetchall()
    payments = [dict(p) for p in payments]

    total_spent = sum(p['amount'] for p in payments)

    fahri = conn.execute("SELECT id FROM users WHERE display_name = 'Fahri'").fetchone()
    metin = conn.execute("SELECT id FROM users WHERE display_name = 'Metin'").fetchone()
    fahri_id = fahri['id'] if fahri else 0
    metin_id = metin['id'] if metin else 0

    fahri_paid  = sum(p['amount'] for p in payments if p['paid_by_user_id'] == fahri_id)
    metin_paid  = sum(p['amount'] for p in payments if p['paid_by_user_id'] == metin_id)

    category_totals = {}
    card_totals = {}
    for p in payments:
        category_totals[p['category']] = category_totals.get(p['category'], 0) + p['amount']
        card_totals[p['card_used']]    = card_totals.get(p['card_used'], 0) + p['amount']

    metin_total_debt = 0
    if fahri and metin:
        dr = conn.execute("SELECT SUM(amount) as t FROM debts WHERE debtor_user_id=? AND creditor_user_id=? AND is_paid=0",
                          (metin_id, fahri_id)).fetchone()
        metin_total_debt = dr['t'] or 0

    trend_labels, trend_data = [], []
    for i in range(5, -1, -1):
        ref = datetime(year, month, 1) - timedelta(days=i * 30)
        m, y = ref.month, ref.year
        sd, ed = f"{y}-{m:02d}-01", f"{y}-{m:02d}-31"
        row = conn.execute("SELECT COALESCE(SUM(amount),0) as t FROM payments WHERE payment_date>=? AND payment_date<=?", (sd, ed)).fetchone()
        trend_labels.append(month_names[m])
        trend_data.append(float(row['t'] or 0))

    bills = conn.execute("SELECT * FROM bills WHERE active = 1").fetchall()
    bill_statuses = []
    for b in bills:
        b = dict(b)
        cycle = conn.execute("SELECT status FROM monthly_cycles WHERE bill_id=? AND year=? AND month=?",
                             (b['id'], year, month)).fetchone()
        status = dict(cycle)['status'] if cycle else 'bekliyor'
        bill_statuses.append({'name': b['name'], 'amount': b['amount'], 'status': status,
                              'subscriber_no': b.get('subscriber_no', '')})

    if request.method == 'POST':
        msg  = f"📊 {month_names[month]} {year} ÖZET\nToplam: {total_spent:.0f}TL | Fahri: {fahri_paid:.0f}TL | Metin: {metin_paid:.0f}TL"
        msg += "\n\nKATEGORILER\n" + "\n".join(f"  {c}: {t:.0f}TL" for c, t in category_totals.items())
        msg += "\n\nKARTLAR\n"     + "\n".join(f"  {c}: {t:.0f}TL" for c, t in card_totals.items())
        notifier.notify_all(msg)
        flash("Rapor SMS olarak gönderildi.", "success")
        return redirect(url_for('raporlar', year=year, month=month))

    conn.close()

    TMPL = """{% extends 'base.html' %}
    {% block content %}
    <div class="d-flex justify-content-between align-items-center mb-4">
        <span class="page-title">&#128202; Raporlar</span>
    </div>
    <form method="GET" class="card p-3 mb-4 d-flex flex-row gap-2">
        <select name="month" class="form-select">
            {% for m in range(1, 13) %}<option value="{{ m }}" {% if m == month %}selected{% endif %}>{{ month_names[m] }}</option>{% endfor %}
        </select>
        <input type="number" name="year" class="form-control" value="{{ year }}" style="max-width:100px;">
        <button type="submit" class="btn btn-primary px-4">Getir</button>
    </form>
    <div class="row g-2 mb-4">
        <div class="col-6"><div class="card p-3 text-center" style="border-left:4px solid var(--primary);">
            <div style="font-size:0.7rem;color:var(--text-muted);font-weight:600;text-transform:uppercase;">Toplam Harcama</div>
            <div style="font-size:1.5rem;font-weight:700;color:var(--primary);">{{ "%.0f"|format(total_spent) }} &#8378;</div>
        </div></div>
        <div class="col-6"><div class="card p-3 text-center" style="border-left:4px solid var(--danger);">
            <div style="font-size:0.7rem;color:var(--text-muted);font-weight:600;text-transform:uppercase;">Metin Borcu</div>
            <div style="font-size:1.5rem;font-weight:700;color:var(--danger);">{{ "%.0f"|format(metin_total_debt) }} &#8378;</div>
        </div></div>
        <div class="col-6"><div class="card p-3 text-center" style="border-left:4px solid #6366f1;">
            <div style="font-size:0.7rem;color:var(--text-muted);font-weight:600;text-transform:uppercase;">Fahri &#214;dedi</div>
            <div style="font-size:1.4rem;font-weight:700;color:#6366f1;">{{ "%.0f"|format(fahri_paid) }} &#8378;</div>
        </div></div>
        <div class="col-6"><div class="card p-3 text-center" style="border-left:4px solid var(--success);">
            <div style="font-size:0.7rem;color:var(--text-muted);font-weight:600;text-transform:uppercase;">Metin &#214;dedi</div>
            <div style="font-size:1.4rem;font-weight:700;color:var(--success);">{{ "%.0f"|format(metin_paid) }} &#8378;</div>
        </div></div>
    </div>
    <div class="card p-3 mb-4">
        <div class="section-title">Son 6 Ay Trendi</div>
        <canvas id="trendChart" height="150"></canvas>
    </div>
    <div class="card p-3 mb-4">
        <div class="section-title mb-3">Kategorilere G&#246;re</div>
        {% if category_totals %}{% for cat, amount in category_totals.items() %}
        <div class="mb-3">
            <div class="d-flex justify-content-between mb-1">
                <span style="font-weight:500;font-size:0.9rem;">{{ cat }}</span>
                <span style="font-weight:600;font-size:0.9rem;">{{ "%.0f"|format(amount) }} &#8378;
                    {% if total_spent > 0 %}<span style="color:var(--text-muted);font-size:0.8rem;">({{ (amount/total_spent*100)|int }}%)</span>{% endif %}
                </span>
            </div>
            <div style="height:6px;background:#e2e8f0;border-radius:3px;overflow:hidden;">
                <div style="height:100%;border-radius:3px;background:var(--primary);width:{% if total_spent > 0 %}{{ (amount/total_spent*100)|int }}%{% else %}0%{% endif %};"></div>
            </div>
        </div>{% endfor %}{% else %}
        <div class="text-muted text-center py-3">Bu ay veri yok.</div>{% endif %}
    </div>
    <div class="card p-3 mb-4">
        <div class="section-title mb-3">Kart Kullan&#305;m&#305;</div>
        {% for card, amount in card_totals.items() %}
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span style="font-weight:500;">{{ card }}</span>
            <div class="d-flex align-items-center gap-2">
                <div style="height:4px;width:80px;background:#e2e8f0;border-radius:2px;overflow:hidden;">
                    <div style="height:100%;background:var(--primary);width:{% if total_spent > 0 %}{{ (amount/total_spent*100)|int }}%{% else %}0%{% endif %};"></div>
                </div>
                <span style="font-weight:700;font-size:0.9rem;">{{ "%.0f"|format(amount) }} &#8378;</span>
            </div>
        </div>{% else %}<div class="text-muted text-center py-3">Bu ay veri yok.</div>{% endfor %}
    </div>
    <div class="card p-3 mb-4">
        <div class="section-title mb-3">{{ month_names[month] }} {{ year }} Fatura Durumu</div>
        {% for b in bill_statuses %}
        <div class="d-flex justify-content-between align-items-center mb-2 p-2" style="border-radius:10px;background:#f8fafc;">
            <div>
                <div style="font-weight:600;font-size:0.9rem;">{{ b.name }}</div>
                {% if b.subscriber_no %}<div style="font-size:0.75rem;color:var(--text-muted);">Abone: {{ b.subscriber_no }}</div>{% endif %}
            </div>
            <div class="d-flex align-items-center gap-2">
                <span style="font-weight:700;font-size:0.9rem;">{{ b.amount }} &#8378;</span>
                {% if b.status == 'odendi' %}<span class="badge" style="background:#d1fae5;color:#065f46;">&#10003; &#214;dendi</span>
                {% else %}<span class="badge" style="background:#fee2e2;color:#991b1b;">&#9203; Bekliyor</span>{% endif %}
            </div>
        </div>{% else %}<div class="text-muted text-center py-3">Fatura yok.</div>{% endfor %}
    </div>
    <form method="POST" class="mb-4">
        <button type="submit" class="btn btn-success btn-lg w-100 py-3 fw-bold" style="border-radius:14px;">&#128241; Raporu SMS Olarak G&#246;nder</button>
    </form>
    {% endblock %}
    {% block scripts %}
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
    <script>
    new Chart(document.getElementById('trendChart'), {
        type: 'bar',
        data: {
            labels: TREND_LABELS_PLACEHOLDER,
            datasets: [{ data: TREND_DATA_PLACEHOLDER, backgroundColor: 'rgba(99,102,241,0.75)', borderRadius: 8, borderSkipped: false }]
        },
        options: { responsive: true, plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true, grid: { color: '#e2e8f0' } }, x: { grid: { display: false } } } }
    });
    </script>
    {% endblock %}
    """

    TMPL = TMPL.replace('TREND_LABELS_PLACEHOLDER', _json.dumps(trend_labels))
    TMPL = TMPL.replace('TREND_DATA_PLACEHOLDER', _json.dumps(trend_data))

    return render_template_string(TMPL, year=year, month=month, month_names=month_names,
        total_spent=total_spent, fahri_paid=fahri_paid, metin_paid=metin_paid,
        metin_total_debt=metin_total_debt, category_totals=category_totals,
        card_totals=card_totals, bill_statuses=bill_statuses)



@app.route('/ayarlar', methods=['GET', 'POST'])
@login_required
def ayarlar():
    conn = database.get_db_connection()
    if request.method == 'POST':
        if 'test_sms' in request.form:
            phone = current_user.phone_number
            if phone:
                res = notifier.send_sms(phone, "Test SMS başarılı! Fatura Takip sistemi çalışıyor.")
                if res:
                    flash("Test SMS başarıyla gönderildi.", "success")
                else:
                    flash("SMS gönderilemedi. API bilgilerini kontrol edin.", "danger")
        else:
            phone = request.form.get('phone')
            password = request.form.get('password')
            
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET phone_number = ? WHERE id = ?", (phone, current_user.id))
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
        <h5 class="mb-4 text-primary fw-bold border-bottom pb-2">Kişisel Bilgiler</h5>
        <div class="mb-3">
            <label class="form-label text-secondary fw-bold">Telefon Numarası</label>
            <input type="text" name="phone" class="form-control form-control-lg" value="{{ current_user.phone_number }}" placeholder="Örn: 5551234567">
        </div>
        <div class="mb-4">
            <label class="form-label text-secondary fw-bold">Yeni Şifre</label>
            <input type="password" name="password" class="form-control form-control-lg" placeholder="Sadece değiştirmek istiyorsanız doldurun">
        </div>
        <button type="submit" class="btn btn-primary btn-lg w-100 py-3 fw-bold shadow">Ayarları Kaydet</button>
    </form>
    
    <form method="POST" class="card p-4 shadow-sm border-0 bg-light">
        <h5 class="mb-3 text-secondary fw-bold">Bağlantı Testi</h5>
        <p class="text-muted small">Bu butona basarak sms-gate.app üzerinden telefonunuza SMS gönderip gönderemediğini test edebilirsiniz.</p>
        <input type="hidden" name="test_sms" value="1">
        <button type="submit" class="btn btn-outline-success btn-lg w-100 py-3 fw-bold">Sistemi Test Et (SMS Gönder)</button>
    </form>
    {% endblock %}
    """)

@app.route('/cron')
def cron_job():
    check_bills_and_notify()
    return "Cron run successfully", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5002)))
