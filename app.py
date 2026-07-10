from flask import Flask, request, redirect, send_file, render_template
import psycopg2
from fpdf import FPDF
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta
import os
import base64
import secrets
import requests
import stripe

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-only-change-in-render')

login_manager = LoginManager(app)
login_manager.login_view = 'login'

stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_PRICE_ID = "price_1Tqmr2QKfprCRWsdLfLubmdF"
APP_URL = "https://quote-app-flfp.onrender.com"


def get_db():
    return psycopg2.connect(os.environ.get('DATABASE_URL'))


def stripe_field(obj, key):
    try:
        return obj[key]
    except (KeyError, AttributeError):
        return None


def build_quote_pdf(path, company_name, owner_email, quote_id, created_at,
                     client_name, client_email, address,
                     service_name, quantity, unit_label, unit_price, additional_charges,
                     total, deposit, signature_name, signed_at, terms_note):
    DARK = (26, 23, 20)
    AMBER = (232, 160, 32)
    LIGHT = (245, 242, 237)
    GREY_TEXT = (90, 84, 76)
    WHITE = (255, 255, 255)

    valid_until = created_at + timedelta(days=30)
    quote_number = f"{quote_id:04d}"

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=18)

    # ---------- Encabezado de marca (oscuro + ámbar) ----------
    pdf.set_fill_color(*DARK)
    pdf.rect(0, 0, 130, 24, "F")
    pdf.set_fill_color(*AMBER)
    pdf.rect(130, 0, 80, 24, "F")

    pdf.set_xy(10, 6)
    pdf.set_text_color(*WHITE)
    pdf.set_font("Arial", "B", 16)
    pdf.cell(115, 8, company_name, ln=2)
    pdf.set_font("Arial", size=9)
    pdf.set_x(10)
    pdf.cell(115, 6, owner_email, ln=1)

    pdf.set_xy(132, 7)
    pdf.set_text_color(*DARK)
    pdf.set_font("Arial", "B", 14)
    pdf.cell(76, 8, "ESTIMATE / QUOTE", align="R")

    pdf.set_y(30)

    # ---------- Bloques FROM / QUOTE FOR ----------
    box_y = pdf.get_y()
    pdf.set_fill_color(*LIGHT)
    pdf.rect(10, box_y, 90, 26, "F")
    pdf.rect(110, box_y, 90, 26, "F")

    pdf.set_xy(14, box_y + 3)
    pdf.set_font("Arial", "B", 8)
    pdf.set_text_color(180, 130, 20)
    pdf.cell(80, 5, "FROM")
    pdf.set_xy(14, box_y + 8)
    pdf.set_text_color(*DARK)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(80, 5, company_name[:34])
    pdf.set_xy(14, box_y + 14)
    pdf.set_font("Arial", size=9)
    pdf.set_text_color(*GREY_TEXT)
    pdf.cell(80, 5, owner_email[:38])

    pdf.set_xy(114, box_y + 3)
    pdf.set_text_color(180, 130, 20)
    pdf.set_font("Arial", "B", 8)
    pdf.cell(80, 5, "QUOTE FOR")
    pdf.set_xy(114, box_y + 8)
    pdf.set_text_color(*DARK)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(80, 5, client_name[:34])
    pdf.set_xy(114, box_y + 14)
    pdf.set_font("Arial", size=9)
    pdf.set_text_color(*GREY_TEXT)
    pdf.multi_cell(85, 5, f"{address}\n{client_email}")

    pdf.set_y(box_y + 32)

    # ---------- Fila de metadatos ----------
    meta_y = pdf.get_y()
    pdf.set_fill_color(*DARK)
    pdf.set_text_color(*WHITE)
    pdf.set_font("Arial", "B", 8)
    col_w = 45
    for label in ["QUOTE #", "DATE", "VALID UNTIL", "SERVICE"]:
        pdf.cell(col_w, 7, label, fill=True, border=0)
    pdf.ln(7)
    pdf.set_text_color(*DARK)
    pdf.set_font("Arial", size=9)
    pdf.set_draw_color(*LIGHT)
    pdf.cell(col_w, 8, quote_number, border=1)
    pdf.cell(col_w, 8, created_at.strftime("%b %d, %Y"), border=1)
    pdf.cell(col_w, 8, valid_until.strftime("%b %d, %Y"), border=1)
    pdf.cell(col_w, 8, service_name[:20], border=1)
    pdf.ln(14)

    # ---------- Tabla de desglose ----------
    pdf.set_font("Arial", "B", 10)
    pdf.set_text_color(*DARK)
    pdf.cell(0, 6, "PROJECT DETAIL", ln=1)
    pdf.set_draw_color(*AMBER)
    pdf.set_line_width(0.6)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(4)

    widths = [75, 25, 25, 30, 25]
    headers = ["Description", "Qty", "Unit", "Unit Price", "Total"]
    pdf.set_fill_color(*DARK)
    pdf.set_text_color(*WHITE)
    pdf.set_font("Arial", "B", 8)
    for w, h in zip(widths, headers):
        pdf.cell(w, 7, h, fill=True)
    pdf.ln(7)

    pdf.set_text_color(*DARK)
    pdf.set_font("Arial", size=9)
    line_total = unit_price * quantity
    row_vals = [service_name[:34], f"{quantity:g}", unit_label[:8], f"${unit_price:,.2f}", f"${line_total:,.2f}"]
    for w, v in zip(widths, row_vals):
        pdf.cell(w, 8, v, border="B")
    pdf.ln(8)

    if additional_charges:
        row_vals = ["Additional Charges", "1", "flat", f"${additional_charges:,.2f}", f"${additional_charges:,.2f}"]
        for w, v in zip(widths, row_vals):
            pdf.cell(w, 8, v, border="B")
        pdf.ln(8)

    pdf.set_fill_color(*AMBER)
    pdf.set_text_color(*DARK)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(155, 9, "TOTAL", fill=True, align="R")
    pdf.cell(25, 9, f"${total:,.2f}", fill=True, align="R")
    pdf.ln(16)

    # ---------- Calendario de pago ----------
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 6, "PAYMENT", ln=1)
    pdf.set_draw_color(*AMBER)
    pdf.set_line_width(0.6)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(4)

    balance = total - deposit
    pdf.set_fill_color(*DARK)
    pdf.set_text_color(*WHITE)
    pdf.set_font("Arial", "B", 8)
    pdf.cell(90, 7, "DEPOSIT DUE NOW", fill=True)
    pdf.cell(90, 7, "BALANCE DUE ON COMPLETION", fill=True)
    pdf.ln(7)
    pdf.set_text_color(*DARK)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(90, 9, f"${deposit:,.2f}", border=1)
    pdf.cell(90, 9, f"${balance:,.2f}", border=1)
    pdf.ln(16)

    # ---------- Términos (si el contratista los definió) ----------
    if terms_note:
        pdf.set_font("Arial", "B", 10)
        pdf.cell(0, 6, "TERMS", ln=1)
        pdf.set_draw_color(*AMBER)
        pdf.set_line_width(0.6)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.set_line_width(0.2)
        pdf.ln(4)
        pdf.set_font("Arial", size=9)
        pdf.set_text_color(*GREY_TEXT)
        pdf.multi_cell(0, 5, terms_note)
        pdf.ln(10)

    # ---------- Firma ----------
    pdf.set_font("Arial", "B", 10)
    pdf.set_text_color(*DARK)
    pdf.cell(0, 6, "ACCEPTANCE", ln=1)
    pdf.set_draw_color(*AMBER)
    pdf.set_line_width(0.6)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(6)
    pdf.set_font("Arial", size=9)
    pdf.set_text_color(*GREY_TEXT)
    if signature_name and signed_at:
        pdf.cell(0, 6, f"Signed electronically by {signature_name} on {signed_at.strftime('%b %d, %Y')}", ln=1)
    else:
        pdf.cell(0, 6, "Awaiting client signature", ln=1)

    pdf.output(path)


def send_email(to_email, subject, text, pdf_base64=None, pdf_filename=None):
    payload = {
        "from": "quotes@qotixo.com",
        "to": [to_email],
        "subject": subject,
        "text": text,
    }
    if pdf_base64 and pdf_filename:
        payload["attachments"] = [{"filename": pdf_filename, "content": pdf_base64}]
    try:
        requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {os.environ.get('RESEND_API_KEY')}"},
            json=payload,
            timeout=15
        )
    except Exception as e:
        print(f"Email error: {e}")


class User(UserMixin):
    def __init__(self, id, email):
        self.id = id
        self.email = email


@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = c.fetchone()
    conn.close()
    if user:
        return User(user[0], user[1])
    return None


def has_active_subscription(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT subscription_status, trial_end FROM users WHERE id = %s", (user_id,))
    row = c.fetchone()
    conn.close()

    if row is None:
        return False

    status, trial_end = row
    now = datetime.utcnow()

    if status == "active":
        return True
    if status == "trialing" and trial_end and trial_end > now:
        return True
    return False


def subscription_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if has_active_subscription(current_user.id):
            return f(*args, **kwargs)

        return redirect("/billing")
    return decorated_function


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS quotes (
            id SERIAL PRIMARY KEY,
            client_name TEXT,
            address TEXT,
            job_type TEXT,
            sqft INTEGER,
            demo TEXT,
            total REAL,
            deposit REAL,
            client_email TEXT,
            user_id INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE,
            password TEXT,
            company_name TEXT,
            price_driveway REAL,
            price_patio REAL,
            price_foundation REAL,
            demo_upcharge REAL
        )
    """)
    c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT")
    c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT")
    c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_status TEXT DEFAULT 'trialing'")
    c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_end TIMESTAMP")
    c.execute("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS token TEXT UNIQUE")
    c.execute("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS signature_name TEXT")
    c.execute("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS signed_at TIMESTAMP")
    c.execute("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS deposit_paid BOOLEAN DEFAULT FALSE")
    c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_connect_id TEXT")
    c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_connect_onboarded BOOLEAN DEFAULT FALSE")
    c.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            name TEXT,
            unit_label TEXT,
            unit_price REAL
        )
    """)
    c.execute("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS service_name TEXT")
    c.execute("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS quantity REAL")
    c.execute("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS unit_label TEXT")
    c.execute("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS additional_charges REAL DEFAULT 0")
    c.execute("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS unit_price REAL")
    c.execute("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()")
    c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_note TEXT")
    c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS services_migrated BOOLEAN DEFAULT FALSE")

    # Migración de una sola vez: traslada los precios viejos (driveway/patio/foundation)
    # de cuentas ya existentes a la nueva tabla de servicios, para que no pierdan sus precios.
    c.execute("""
        INSERT INTO services (user_id, name, unit_label, unit_price)
        SELECT id, 'Driveway', 'sqft', price_driveway FROM users
        WHERE price_driveway IS NOT NULL AND services_migrated = FALSE
    """)
    c.execute("""
        INSERT INTO services (user_id, name, unit_label, unit_price)
        SELECT id, 'Patio', 'sqft', price_patio FROM users
        WHERE price_patio IS NOT NULL AND services_migrated = FALSE
    """)
    c.execute("""
        INSERT INTO services (user_id, name, unit_label, unit_price)
        SELECT id, 'Foundation', 'sqft', price_foundation FROM users
        WHERE price_foundation IS NOT NULL AND services_migrated = FALSE
    """)
    c.execute("UPDATE users SET services_migrated = TRUE WHERE services_migrated = FALSE")
    conn.commit()
    conn.close()


init_db()


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])
        company_name = request.form["company_name"]
        trial_end = datetime.utcnow() + timedelta(days=14)
        conn = get_db()
        c = conn.cursor()
        try:
            c.execute("""INSERT INTO users
                (email, password, company_name, price_driveway, price_patio, price_foundation, demo_upcharge, subscription_status, trial_end, services_migrated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE) RETURNING id""",
                      (email, password, company_name, 25, 22, 28, 7, "trialing", trial_end))
            new_user_id = c.fetchone()[0]

            starter_services = [
                ("Driveway", "sqft", 25.0),
                ("Patio", "sqft", 22.0),
                ("Foundation", "sqft", 28.0),
            ]
            for name, unit_label, unit_price in starter_services:
                c.execute(
                    "INSERT INTO services (user_id, name, unit_label, unit_price) VALUES (%s, %s, %s, %s)",
                    (new_user_id, name, unit_label, unit_price)
                )
            conn.commit()

            send_email(
                "estimates@precisionconcreteinc.net",
                "New Qotixo signup",
                f"New user registered:\n\nCompany: {company_name}\nEmail: {email}"
            )

        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            conn.close()
            return render_template(
                "register.html",
                error='That email is already registered. Please <a href="/login">log in</a> instead.'
            )
        conn.close()
        return redirect("/login")
    return render_template("register.html", error=None)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = c.fetchone()
        conn.close()
        if user and check_password_hash(user[2], password):
            login_user(User(user[0], user[1]))
            return redirect("/")
        return render_template("login.html", error="Invalid email or password")
    return render_template("login.html", error=None)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")


@app.route("/billing")
@login_required
def billing():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT subscription_status, trial_end, company_name FROM users WHERE id = %s", (current_user.id,))
    status, trial_end, company_name = c.fetchone()
    conn.close()

    now = datetime.utcnow()
    if status == "active":
        message = "Your subscription is active. Thank you!"
        show_button = False
    elif status == "trialing" and trial_end and trial_end > now:
        days_left = (trial_end - now).days
        message = f"You're on a free trial. {days_left} day(s) left."
        show_button = True
    else:
        message = "Your trial has ended or your subscription is inactive. Subscribe to keep using Qotixo."
        show_button = True

    return render_template("billing.html", message=message, show_button=show_button, active_nav="billing", company_name=company_name)


@app.route("/subscribe")
@login_required
def subscribe():
    checkout_session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
        success_url=f"{APP_URL}/billing",
        cancel_url=f"{APP_URL}/billing",
        client_reference_id=str(current_user.id),
        customer_email=current_user.email,
    )
    return redirect(checkout_session.url, code=303)


@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")
    endpoint_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        return "Invalid signature", 400

    conn = get_db()
    c = conn.cursor()

    if event["type"] == "checkout.session.completed":
        session_obj = event["data"]["object"]
        metadata = stripe_field(session_obj, "metadata") or {}
        quote_token = stripe_field(metadata, "quote_token")

        if quote_token:
            c.execute("UPDATE quotes SET deposit_paid = TRUE WHERE token = %s", (quote_token,))
            conn.commit()

            c.execute("""
                SELECT q.client_name, q.deposit, u.email
                FROM quotes q JOIN users u ON q.user_id = u.id
                WHERE q.token = %s
            """, (quote_token,))
            row = c.fetchone()
            if row:
                client_name, deposit, owner_email = row
                send_email(
                    owner_email,
                    f"Deposit paid: {client_name}",
                    f"{client_name} just paid their deposit of ${deposit:,.2f}. You're ready to schedule the job."
                )
        else:
            user_id = stripe_field(session_obj, "client_reference_id")
            customer_id = stripe_field(session_obj, "customer")
            subscription_id = stripe_field(session_obj, "subscription")
            if user_id and subscription_id:
                user_id = int(user_id)
                current_sub = stripe.Subscription.retrieve(subscription_id)
                current_status = stripe_field(current_sub, "status")
                c.execute(
                    "UPDATE users SET stripe_customer_id = %s, stripe_subscription_id = %s, subscription_status = %s WHERE id = %s",
                    (customer_id, subscription_id, current_status, user_id)
                )
                conn.commit()

    elif event["type"] == "customer.subscription.updated":
        sub = event["data"]["object"]
        customer_id = stripe_field(sub, "customer")
        status = stripe_field(sub, "status")
        c.execute(
            "UPDATE users SET subscription_status = %s WHERE stripe_customer_id = %s",
            (status, customer_id)
        )
        conn.commit()

    elif event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        customer_id = stripe_field(sub, "customer")
        c.execute(
            "UPDATE users SET subscription_status = 'canceled' WHERE stripe_customer_id = %s",
            (customer_id,)
        )
        conn.commit()

    conn.close()
    return "", 200


@app.route("/connect-stripe")
@login_required
def connect_stripe():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT stripe_connect_id FROM users WHERE id = %s", (current_user.id,))
    connect_id = c.fetchone()[0]

    if not connect_id:
        account = stripe.Account.create(
            type="express",
            email=current_user.email,
            capabilities={"transfers": {"requested": True}},
        )
        connect_id = account.id
        c.execute("UPDATE users SET stripe_connect_id = %s WHERE id = %s", (connect_id, current_user.id))
        conn.commit()
    conn.close()

    account_link = stripe.AccountLink.create(
        account=connect_id,
        refresh_url=f"{APP_URL}/connect-stripe",
        return_url=f"{APP_URL}/connect-stripe/return",
        type="account_onboarding",
    )
    return redirect(account_link.url, code=303)


@app.route("/connect-stripe/return")
@login_required
def connect_stripe_return():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT stripe_connect_id FROM users WHERE id = %s", (current_user.id,))
    connect_id = c.fetchone()[0]

    if connect_id:
        account = stripe.Account.retrieve(connect_id)
        onboarded = bool(stripe_field(account, "charges_enabled"))
        c.execute("UPDATE users SET stripe_connect_onboarded = %s WHERE id = %s", (onboarded, current_user.id))
        conn.commit()
    conn.close()
    return redirect("/settings")


@app.route("/services", methods=["GET", "POST"])
@login_required
@subscription_required
def services():
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        name = request.form["name"].strip()
        unit_label = request.form["unit_label"].strip()
        unit_price = float(request.form["unit_price"])
        if name and unit_label:
            c.execute(
                "INSERT INTO services (user_id, name, unit_label, unit_price) VALUES (%s, %s, %s, %s)",
                (current_user.id, name, unit_label, unit_price)
            )
            conn.commit()
        conn.close()
        return redirect("/services")

    c.execute("SELECT id, name, unit_label, unit_price FROM services WHERE user_id = %s ORDER BY id", (current_user.id,))
    all_services = c.fetchall()
    c.execute("SELECT company_name FROM users WHERE id = %s", (current_user.id,))
    company_name = c.fetchone()[0]
    conn.close()
    return render_template("services.html", services=all_services, active_nav="services", company_name=company_name)


@app.route("/services/<int:id>/delete")
@login_required
@subscription_required
def delete_service(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM services WHERE id = %s AND user_id = %s", (id, current_user.id))
    conn.commit()
    conn.close()
    return redirect("/services")


@app.route("/settings", methods=["GET", "POST"])
@login_required
@subscription_required
def settings():
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        company_name = request.form["company_name"]
        terms_note = request.form.get("terms_note", "").strip()
        c.execute("UPDATE users SET company_name = %s, terms_note = %s WHERE id = %s", (company_name, terms_note, current_user.id))
        conn.commit()
        conn.close()
        return redirect("/")

    c.execute("SELECT company_name, stripe_connect_onboarded, terms_note FROM users WHERE id = %s", (current_user.id,))
    company_name, stripe_connect_onboarded, terms_note = c.fetchone()
    conn.close()

    return render_template(
        "settings.html",
        company_name=company_name,
        stripe_connect_onboarded=stripe_connect_onboarded,
        terms_note=terms_note,
        active_nav="settings"
    )


@app.route("/")
def home():
    if not current_user.is_authenticated:
        return render_template("landing.html")

    if not has_active_subscription(current_user.id):
        return redirect("/billing")

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT company_name FROM users WHERE id = %s", (current_user.id,))
    company_name = c.fetchone()[0]
    c.execute("SELECT id, name, unit_label, unit_price FROM services WHERE user_id = %s ORDER BY id", (current_user.id,))
    user_services = c.fetchall()
    c.execute("""
        SELECT
            COUNT(*),
            COALESCE(SUM(CASE WHEN deposit_paid THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(total), 0)
        FROM quotes WHERE user_id = %s
    """, (current_user.id,))
    quotes_count, paid_count, pipeline_value = c.fetchone()
    conn.close()
    return render_template(
        "home.html",
        company_name=company_name,
        services=user_services,
        has_services=len(user_services) > 0,
        quotes_count=quotes_count,
        paid_count=paid_count,
        pipeline_value=pipeline_value,
        active_nav="home"
    )


@app.route("/quote", methods=["POST"])
@login_required
@subscription_required
def quote():
    client_name = request.form["client_name"]
    client_email = request.form["client_email"]
    address = request.form["address"]
    service_id = int(request.form["service_id"])
    quantity = float(request.form["quantity"])
    additional_charges = float(request.form.get("additional_charges") or 0)

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT company_name, terms_note FROM users WHERE id = %s", (current_user.id,))
    company_name, terms_note = c.fetchone()
    c.execute("SELECT name, unit_label, unit_price FROM services WHERE id = %s AND user_id = %s", (service_id, current_user.id))
    service_row = c.fetchone()
    conn.close()

    if service_row is None:
        return redirect("/")

    service_name, unit_label, unit_price = service_row

    total = (unit_price * quantity) + additional_charges
    deposit = min(1000, total * 0.10)

    conn = get_db()
    c = conn.cursor()
    quote_token = secrets.token_urlsafe(16)
    c.execute("""
        INSERT INTO quotes
            (client_name, address, job_type, sqft, demo, total, deposit, client_email, user_id, token,
             service_name, quantity, unit_label, additional_charges, unit_price)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, created_at
    """, (
        client_name, address, service_name, int(round(quantity)), ("yes" if additional_charges > 0 else "no"),
        total, deposit, client_email, current_user.id, quote_token,
        service_name, quantity, unit_label, additional_charges, unit_price
    ))
    quote_id, created_at = c.fetchone()
    conn.commit()
    conn.close()

    path = f"quote_{client_name}.pdf"
    build_quote_pdf(
        path, company_name, current_user.email, quote_id, created_at,
        client_name, client_email, address,
        service_name, quantity, unit_label, unit_price, additional_charges,
        total, deposit, None, None, terms_note
    )

    with open(path, "rb") as f:
        pdf_base64 = base64.b64encode(f.read()).decode("utf-8")

    send_email(
        client_email,
        f"Your Quote from {company_name}",
        f"Hi {client_name},\n\nPlease find your quote attached.\n\nTotal: ${total:,.2f}\nDeposit Due: ${deposit:,.2f}\n\nTo accept this quote and pay your deposit online, click here:\n{APP_URL}/view/{quote_token}\n\nThank you,\n{company_name}",
        pdf_base64,
        f"quote_{client_name}.pdf"
    )

    send_email(
        current_user.email,
        f"New lead: {client_name}",
        f"You just generated a new quote.\n\nClient: {client_name}\nEmail: {client_email}\nAddress: {address}\nService: {service_name}\nQuantity: {quantity:g} {unit_label}\nAdditional Charges: ${additional_charges:,.2f}\nTotal: ${total:,.2f}\nDeposit Due: ${deposit:,.2f}"
    )

    return render_template(
        "quote_summary.html",
        client_name=client_name,
        address=address,
        service_name=service_name,
        quantity=quantity,
        unit_label=unit_label,
        additional_charges=additional_charges,
        total=total,
        deposit=deposit,
        active_nav="quotes",
        company_name=company_name
    )


@app.route("/dashboard")
@login_required
@subscription_required
def dashboard():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT
            COUNT(*),
            COALESCE(SUM(total), 0),
            COALESCE(SUM(CASE WHEN signed_at IS NOT NULL THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN deposit_paid THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN deposit_paid THEN deposit ELSE 0 END), 0)
        FROM quotes WHERE user_id = %s
    """, (current_user.id,))
    total_quotes, pipeline_value, signed_count, paid_count, deposits_collected = c.fetchone()
    c.execute("SELECT company_name FROM users WHERE id = %s", (current_user.id,))
    company_name = c.fetchone()[0]
    conn.close()

    signed_rate = round((signed_count / total_quotes) * 100) if total_quotes else 0
    paid_rate = round((paid_count / total_quotes) * 100) if total_quotes else 0

    return render_template(
        "dashboard.html",
        total_quotes=total_quotes,
        pipeline_value=pipeline_value,
        signed_count=signed_count,
        paid_count=paid_count,
        deposits_collected=deposits_collected,
        signed_rate=signed_rate,
        paid_rate=paid_rate,
        active_nav="dashboard",
        company_name=company_name
    )


@app.route("/quotes")
@login_required
@subscription_required
def view_quotes():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT id, client_name, service_name, total, signed_at, deposit_paid
        FROM quotes WHERE user_id = %s ORDER BY id DESC
    """, (current_user.id,))
    all_quotes = c.fetchall()
    c.execute("SELECT company_name FROM users WHERE id = %s", (current_user.id,))
    company_name = c.fetchone()[0]
    conn.close()
    return render_template("quotes.html", quotes=all_quotes, active_nav="quotes", company_name=company_name)


@app.route("/view/<token>")
def view_quote(token):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT q.client_name, q.address, q.service_name, q.quantity, q.unit_label, q.additional_charges, q.total, q.deposit,
               q.signature_name, q.signed_at, q.deposit_paid, u.company_name, u.stripe_connect_onboarded
        FROM quotes q JOIN users u ON q.user_id = u.id
        WHERE q.token = %s
    """, (token,))
    row = c.fetchone()
    conn.close()

    if row is None:
        return "Quote not found", 404

    (client_name, address, service_name, quantity, unit_label, additional_charges, total, deposit,
     signature_name, signed_at, deposit_paid, company_name, contractor_can_collect) = row

    return render_template(
        "view_quote.html",
        token=token,
        company_name=company_name,
        client_name=client_name,
        address=address,
        service_name=service_name,
        quantity=quantity,
        unit_label=unit_label,
        additional_charges=additional_charges,
        total=total,
        deposit=deposit,
        signature_name=signature_name,
        signed_at=signed_at,
        deposit_paid=deposit_paid,
        contractor_can_collect=contractor_can_collect
    )


@app.route("/view/<token>/sign", methods=["POST"])
def sign_quote(token):
    signature_name = request.form.get("signature_name", "").strip()
    if not signature_name:
        return redirect(f"/view/{token}")

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT client_name, user_id FROM quotes WHERE token = %s", (token,))
    row = c.fetchone()
    if row is None:
        conn.close()
        return "Quote not found", 404

    client_name, user_id = row
    c.execute(
        "UPDATE quotes SET signature_name = %s, signed_at = %s WHERE token = %s",
        (signature_name, datetime.utcnow(), token)
    )
    conn.commit()

    c.execute("SELECT email, company_name FROM users WHERE id = %s", (user_id,))
    owner_email, company_name = c.fetchone()
    conn.close()

    send_email(
        owner_email,
        f"Quote signed: {client_name}",
        f"{client_name} just accepted their quote by signing as '{signature_name}'."
    )

    return redirect(f"/view/{token}")


@app.route("/view/<token>/pay")
def pay_deposit(token):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT q.client_name, q.client_email, q.deposit, q.signed_at, q.deposit_paid,
               u.stripe_connect_id, u.stripe_connect_onboarded
        FROM quotes q JOIN users u ON q.user_id = u.id
        WHERE q.token = %s
    """, (token,))
    row = c.fetchone()
    conn.close()

    if row is None:
        return "Quote not found", 404

    client_name, client_email, deposit, signed_at, deposit_paid, connect_id, onboarded = row

    if not signed_at:
        return redirect(f"/view/{token}")

    if deposit_paid:
        return redirect(f"/view/{token}")

    if not onboarded or not connect_id:
        return redirect(f"/view/{token}")

    checkout_session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": f"Deposit for {client_name}"},
                "unit_amount": int(round(deposit * 100)),
            },
            "quantity": 1,
        }],
        payment_intent_data={
            "transfer_data": {"destination": connect_id}
        },
        success_url=f"{APP_URL}/view/{token}",
        cancel_url=f"{APP_URL}/view/{token}",
        customer_email=client_email,
        metadata={"quote_token": token},
    )
    return redirect(checkout_session.url, code=303)


@app.route("/remind/<int:id>")
@login_required
@subscription_required
def remind_quote(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT q.client_name, q.client_email, q.token, q.signed_at, u.company_name
        FROM quotes q JOIN users u ON q.user_id = u.id
        WHERE q.id = %s AND q.user_id = %s
    """, (id, current_user.id))
    row = c.fetchone()
    conn.close()

    if row is None:
        return redirect("/quotes")

    client_name, client_email, token, signed_at, company_name = row

    if not signed_at and token:
        send_email(
            client_email,
            f"Reminder: Your Quote from {company_name}",
            f"Hi {client_name},\n\nJust a reminder that your quote from {company_name} is still waiting for you.\n\nView and accept it here:\n{APP_URL}/view/{token}\n\nThank you,\n{company_name}"
        )

    return redirect("/quotes")


@app.route("/delete/<int:id>")
@login_required
@subscription_required
def delete_quote(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM quotes WHERE id = %s AND user_id = %s", (id, current_user.id))
    conn.commit()
    conn.close()
    return redirect("/quotes")


@app.route("/pdf/<int:id>")
@login_required
@subscription_required
def generate_pdf(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT client_name, address, service_name, quantity, unit_label, additional_charges, total, deposit,
               unit_price, created_at, signature_name, signed_at
        FROM quotes WHERE id = %s AND user_id = %s
    """, (id, current_user.id))
    q = c.fetchone()
    c.execute("SELECT company_name, terms_note FROM users WHERE id = %s", (current_user.id,))
    company_name, terms_note = c.fetchone()
    conn.close()

    if q is None:
        return "Quote not found", 404

    (client_name, address, service_name, quantity, unit_label, additional_charges, total, deposit,
     unit_price, created_at, signature_name, signed_at) = q

    path = f"quote_{id}.pdf"
    build_quote_pdf(
        path, company_name, current_user.email, id, created_at,
        client_name, "", address,
        service_name, quantity, unit_label, unit_price or 0, additional_charges or 0,
        total, deposit, signature_name, signed_at, terms_note
    )
    return send_file(path, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)