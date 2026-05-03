import os
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
        body { padding-bottom: 70px; background-color: #f8f9fa; }
        .navbar-bottom { position: fixed; bottom: 0; width: 100%; z-index: 1030; background-color: #fff; box-shadow: 0 -2px 10px rgba(0,0,0,0.1); }
        .nav-item { text-align: center; font-size: 0.85rem; }
        .nav-link { padding: 10px 5px; color: #6c757d; }
        .nav-link.active { color: #0d6efd; font-weight: bold; }
        .nav-icon { display: block; font-size: 1.2rem; margin-bottom: 2px; }
        .card { border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: none; margin-bottom: 15px; }
        .dashboard-debt { font-size: 2.5rem; font-weight: bold; }
        .calendar-table th, .calendar-table td { text-align: center; vertical-align: top; width: 14%; height: 80px; }
        .day-number { font-weight: bold; }
        .cal-item { font-size: 0.75rem; border-radius: 4px; padding: 2px; margin-top: 2px; }
        .cal-item.success { background-color: #d1e7dd; color: #0f5132; }
        .cal-item.warning { background-color: #fff3cd; color: #664d03; }
        .cal-item.danger { background-color: #f8d7da; color: #842029; }
        
        /* Custom Radio Buttons for larger select UX */
        .btn-check-custom + .btn { border-radius: 10px; padding: 12px; font-size: 1.1rem; }
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
    <nav class="navbar-bottom d-flex justify-content-around py-2">
        <a href="{{ url_for('dashboard') }}" class="nav-link {% if request.endpoint == 'dashboard' %}active{% endif %}">
            <span class="nav-icon">🏠</span> Dash
        </a>
        <a href="{{ url_for('faturalar') }}" class="nav-link {% if request.endpoint in ['faturalar', 'kategoriler'] %}active{% endif %}">
            <span class="nav-icon">📄</span> Fatura
        </a>
        <a href="{{ url_for('odeme_kaydet') }}" class="nav-link {% if request.endpoint == 'odeme_kaydet' %}active{% endif %}">
            <span class="nav-icon">💳</span> Öde
        </a>
        <a href="{{ url_for('borclar') }}" class="nav-link {% if request.endpoint == 'borclar' %}active{% endif %}">
            <span class="nav-icon">🤝</span> Borç
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
    if request.endpoint not in ['setup', 'static']:
        conn = database.get_db_connection()
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        conn.close()
        if user_count == 0:
            return redirect(url_for('setup'))

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    conn = database.get_db_connection()
    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
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
    <div class="d-flex justify-content-between align-items-center mb-3">
        <h3>Dashboard</h3>
        <a href="{{ url_for('ayarlar') }}" class="btn btn-sm btn-outline-secondary">Ayarlar</a>
    </div>
    
    <div class="card p-4 mb-4 text-center bg-primary text-white shadow-sm">
        <h5 class="opacity-75">Metin'in Toplam Borcu</h5>
        <div class="dashboard-debt">{{ metin_debt }} TL</div>
    </div>
    
    <h5 class="mb-3 text-secondary">Bu Ay Bekleyen Faturalar</h5>
    <div class="row">
        {% for b in dashboard_bills %}
        <div class="col-6 col-md-4 mb-3">
            <div class="card p-3 h-100 shadow-sm border-{{ b.color }} text-{{ 'dark' if b.color in ['warning', 'light'] else 'white' }} bg-{{ b.color }} position-relative">
                {% if b.is_autopay %}
                <span class="badge bg-dark position-absolute top-0 end-0 m-2">Oto</span>
                {% endif %}
                <div class="fw-bold fs-6 mt-1">{{ b.name }}</div>
                <div class="fs-5">{{ b.amount }} TL</div>
            </div>
        </div>
        {% else %}
        <div class="col-12"><p class="text-muted">Fatura bulunamadı.</p></div>
        {% endfor %}
    </div>
    
    <h5 class="mt-4 mb-3 text-secondary">Son 5 Ödeme</h5>
    <div class="list-group mb-4 shadow-sm rounded">
        {% for p in payments %}
        <div class="list-group-item">
            <div class="d-flex w-100 justify-content-between">
                <h6 class="mb-1 fw-bold">{{ p.bill_name }}</h6>
                <small class="text-muted">{{ p.payment_date }}</small>
            </div>
            <p class="mb-1 text-secondary">{{ p.payer_name }} ödedi ({{ p.card_used }})</p>
            <small class="fw-bold fs-6 text-success">{{ p.amount }} TL</small>
        </div>
        {% else %}
        <div class="list-group-item text-muted text-center py-4">Henüz ödeme yok.</div>
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
            is_recurring = 1 if request.form.get('is_recurring') == 'on' else 0
            is_autopay = 1 if request.form.get('is_autopay') == 'on' else 0
            
            conn.execute('''
                INSERT INTO bills (name, owner, amount, due_day, last_payment_day, category, is_recurring, is_autopay)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (name, "Ortak", amount, due_day, last_payment_day, category, is_recurring, is_autopay))
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
            <h5 class="mb-1">{{ b.name }} 
                <span class="badge bg-secondary ms-1">{{ b.category }}</span>
                {% if b.is_autopay %}<span class="badge bg-dark ms-1">Otomatik</span>{% endif %}
            </h5>
            <form method="POST" class="d-inline" onsubmit="return confirm('Bu faturayı silmek istediğinize emin misiniz?');">
                <input type="hidden" name="delete_id" value="{{ b.id }}">
                <button class="btn btn-sm btn-outline-danger">Sil</button>
            </form>
        </div>
        <div class="text-muted small mb-3">Tekrarlı: <strong>{{ 'Evet' if b.is_recurring else 'Hayır' }}</strong></div>
        <div class="d-flex justify-content-between align-items-end bg-light p-2 rounded">
            <div class="small">
                <div>Ödeme Günü: <strong>Ayın {{ b.due_day }}. günü</strong></div>
                <div>Son Gün: <strong class="text-danger">Ayın {{ b.last_payment_day }}. günü</strong></div>
            </div>
            <div class="fw-bold fs-4 text-primary">{{ b.amount }} TL</div>
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
        
        payer = conn.execute("SELECT * FROM users WHERE display_name = ?", (paid_by_display,)).fetchone()
        bill = conn.execute("SELECT * FROM bills WHERE id = ?", (bill_id,)).fetchone()
        
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
        cursor.execute("INSERT INTO monthly_cycles (bill_id, year, month, status, payment_id) VALUES (?, ?, ?, 'odendi', ?)",
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
    year = int(request.args.get('year', datetime.now().year))
    month = int(request.args.get('month', datetime.now().month))
    
    conn = database.get_db_connection()
    
    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year}-{month:02d}-31"
    
    payments = conn.execute('''
        SELECT p.*, b.category 
        FROM payments p
        JOIN bills b ON p.bill_id = b.id
        WHERE p.payment_date >= ? AND p.payment_date <= ?
    ''', (start_date, end_date)).fetchall()
    
    total_spent = sum(p['amount'] for p in payments)
    
    fahri = conn.execute("SELECT id FROM users WHERE display_name = 'Fahri'").fetchone()
    metin = conn.execute("SELECT id FROM users WHERE display_name = 'Metin'").fetchone()
    
    fahri_paid = sum(p['amount'] for p in payments if p['paid_by_user_id'] == (fahri['id'] if fahri else 0))
    metin_paid = sum(p['amount'] for p in payments if p['paid_by_user_id'] == (metin['id'] if metin else 0))
    
    category_totals = {}
    card_totals = {}
    for p in payments:
        cat = p['category']
        card = p['card_used']
        category_totals[cat] = category_totals.get(cat, 0) + p['amount']
        card_totals[card] = card_totals.get(card, 0) + p['amount']
        
    payment_ids = [p['id'] for p in payments]
    if payment_ids:
        placeholders = ','.join('?' * len(payment_ids))
        opened_debts = conn.execute(f"SELECT SUM(amount) as t FROM debts WHERE payment_id IN ({placeholders})", payment_ids).fetchone()['t'] or 0
    else:
        opened_debts = 0
        
    closed_debts = conn.execute("SELECT SUM(amount) as t FROM debts WHERE paid_date >= ? AND paid_date <= ?", (start_date, end_date)).fetchone()['t'] or 0
    
    month_names = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
    
    if request.method == 'POST':
        msg = f"📊 {month_names[month]} {year} OZETI\nToplam: {total_spent}TL\nFahri: {fahri_paid}TL | Metin: {metin_paid}TL\n"
        msg += "\n--KARTLAR--\n"
        for c, t in card_totals.items():
            msg += f"{c}: {t}TL\n"
        msg += "\n--KATEGORILER--\n"
        for c, t in category_totals.items():
            msg += f"{c}: {t}TL\n"
            
        notifier.notify_all(msg)
        flash("Detaylı rapor SMS olarak gönderildi.", "success")
        return redirect(url_for('raporlar', year=year, month=month))
        
    conn.close()
    
    return render_template_string("""{% extends 'base.html' %}
    {% block content %}
    <h3 class="mb-4">Aylık Raporlar</h3>
    <form method="GET" class="d-flex mb-4 gap-2 bg-white p-3 rounded shadow-sm">
        <select name="month" class="form-select form-select-lg">
            {% for m in range(1, 13) %}
            <option value="{{ m }}" {% if m == month %}selected{% endif %}>{{ month_names[m] }}</option>
            {% endfor %}
        </select>
        <input type="number" name="year" class="form-control form-control-lg" value="{{ year }}" style="max-width: 120px;">
        <button type="submit" class="btn btn-primary btn-lg px-4">Getir</button>
    </form>
    
    <div class="card p-4 shadow-sm border-0 bg-white">
        <h4 class="text-center mb-4 text-primary fw-bold border-bottom pb-3">{{ month_names[month] }} {{ year }} Özeti</h4>
        
        <div class="row text-center mb-4 bg-light rounded p-3 shadow-sm mx-1">
            <div class="col-12 mb-3">
                <div class="text-muted fw-bold">Toplam Harcama</div>
                <h2 class="text-primary fw-bold">{{ total_spent }} TL</h2>
            </div>
            <div class="col-6 border-end border-2">
                <div class="text-muted fw-bold">Fahri Ödedi</div>
                <div class="fw-bold fs-4">{{ fahri_paid }} TL</div>
            </div>
            <div class="col-6">
                <div class="text-muted fw-bold">Metin Ödedi</div>
                <div class="fw-bold fs-4">{{ metin_paid }} TL</div>
            </div>
        </div>
        
        <h5 class="fw-bold text-secondary mt-4">Kartlara Göre Harcamalar</h5>
        <div class="list-group mb-4 shadow-sm">
            {% for card, total in card_totals.items() %}
            <div class="list-group-item d-flex justify-content-between align-items-center">
                <span>{{ card }}</span>
                <span class="fw-bold fs-5">{{ total }} TL</span>
            </div>
            {% else %}
            <div class="list-group-item text-muted text-center py-3">Veri yok.</div>
            {% endfor %}
        </div>
        
        <h5 class="fw-bold text-secondary">Kategorilere Göre Harcamalar</h5>
        <div class="list-group mb-4 shadow-sm">
            {% for cat, total in category_totals.items() %}
            <div class="list-group-item d-flex justify-content-between align-items-center">
                <span>{{ cat }}</span>
                <span class="fw-bold fs-5">{{ total }} TL</span>
            </div>
            {% else %}
            <div class="list-group-item text-muted text-center py-3">Veri yok.</div>
            {% endfor %}
        </div>
        
        <form method="POST" class="mt-4">
            <button type="submit" class="btn btn-success btn-lg w-100 py-3 fw-bold shadow"><span class="nav-icon d-inline me-2">📱</span> Raporu SMS Olarak Gönder</button>
        </form>
    </div>
    {% endblock %}
    """, year=year, month=month, month_names=month_names, total_spent=total_spent, fahri_paid=fahri_paid, metin_paid=metin_paid, opened_debts=opened_debts, closed_debts=closed_debts, category_totals=category_totals, card_totals=card_totals)

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
