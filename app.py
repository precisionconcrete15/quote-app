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


def subscription_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT subscription_status, trial_end FROM users WHERE id = %s", (current_user.id,))
        row = c.fetchone()
        conn.close()

        if row is None:
            return redirect("/billing")

        status, trial_end = row
        now = datetime.utcnow()

        if status == "active":
            return f(*args, **kwargs)

        if status == "trialing" and trial_end and trial_end > now:
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
                (email, password, company_name, price_driveway, price_patio, price_foundation, demo_upcharge, subscription_status, trial_end)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                      (email, password, company_name, 25, 22, 28, 7, "trialing", trial_end))
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
    c.execute("SELECT subscription_status, trial_end FROM users WHERE id = %s", (current_user.id,))
    status, trial_end = c.fetchone()
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

    return render_template("billing.html", message=message, show_button=show_button)


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


@app.route("/settings", methods=["GET", "POST"])
@login_required
@subscription_required
def settings():
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        company_name = request.form["company_name"]
        price_driveway = float(request.form["price_driveway"])
        price_patio = float(request.form["price_patio"])
        price_foundation = float(request.form["price_foundation"])
        demo_upcharge = float(request.form["demo_upcharge"])

        c.execute("""
            UPDATE users
            SET company_name = %s, price_driveway = %s, price_patio = %s, price_foundation = %s, demo_upcharge = %s
            WHERE id = %s
        """, (company_name, price_driveway, price_patio, price_foundation, demo_upcharge, current_user.id))
        conn.commit()
        conn.close()
        return redirect("/")

    c.execute("SELECT company_name, price_driveway, price_patio, price_foundation, demo_upcharge, stripe_connect_onboarded FROM users WHERE id = %s", (current_user.id,))
    user_data = c.fetchone()
    conn.close()

    company_name, price_driveway, price_patio, price_foundation, demo_upcharge, stripe_connect_onboarded = user_data

    return render_template(
        "settings.html",
        company_name=company_name,
        price_driveway=price_driveway,
        price_patio=price_patio,
        price_foundation=price_foundation,
        demo_upcharge=demo_upcharge,
        stripe_connect_onboarded=stripe_connect_onboarded
    )


@app.route("/")
@login_required
@subscription_required
def home():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT company_name FROM users WHERE id = %s", (current_user.id,))
    company_name = c.fetchone()[0]
    conn.close()
    return render_template("home.html", company_name=company_name)


@app.route("/quote", methods=["POST"])
@login_required
@subscription_required
def quote():
    client_name = request.form["client_name"]
    client_email = request.form["client_email"]
    address = request.form["address"]
    sqft = int(request.form["sqft"])
    job_type = request.form["job_type"]
    demo = request.form["demo"]

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT company_name, price_driveway, price_patio, price_foundation, demo_upcharge FROM users WHERE id = %s", (current_user.id,))
    user_row = c.fetchone()
    conn.close()

    company_name, price_driveway, price_patio, price_foundation, demo_upcharge = user_row

    if job_type == "driveway":
        price_per_sqft = price_driveway
    elif job_type == "patio":
        price_per_sqft = price_patio
    else:
        price_per_sqft = price_foundation

    if demo == "yes":
        price_per_sqft += demo_upcharge

    total = price_per_sqft * sqft
    deposit = min(1000, total * 0.10)

    conn = get_db()
    c = conn.cursor()
    quote_token = secrets.token_urlsafe(16)
    c.execute("INSERT INTO quotes (client_name, address, job_type, sqft, demo, total, deposit, client_email, user_id, token) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
              (client_name, address, job_type, sqft, demo, total, deposit, client_email, current_user.id, quote_token))
    conn.commit()
    conn.close()
    path = f"quote_{client_name}.pdf"
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 20)
    pdf.cell(0, 15, company_name, ln=True)
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, f"Client: {client_name}", ln=True)
    pdf.cell(0, 10, f"Address: {address}", ln=True)
    pdf.cell(0, 10, f"Job Type: {job_type}", ln=True)
    pdf.cell(0, 10, f"Square Footage: {sqft}", ln=True)
    pdf.cell(0, 10, f"Demo: {demo}", ln=True)
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, f"Total: ${total:,.2f}", ln=True)
    pdf.cell(0, 10, f"Deposit Due: ${deposit:,.2f}", ln=True)
    pdf.output(path)

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
        f"You just generated a new quote.\n\nClient: {client_name}\nEmail: {client_email}\nAddress: {address}\nJob Type: {job_type}\nSquare Footage: {sqft}\nDemo: {demo}\nTotal: ${total:,.2f}\nDeposit Due: ${deposit:,.2f}"
    )

    return render_template(
        "quote_summary.html",
        client_name=client_name,
        address=address,
        job_type=job_type,
        sqft=sqft,
        demo=demo,
        total=total,
        deposit=deposit
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
        paid_rate=paid_rate
    )


@app.route("/quotes")
@login_required
@subscription_required
def view_quotes():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM quotes WHERE user_id = %s", (current_user.id,))
    all_quotes = c.fetchall()
    conn.close()
    return render_template("quotes.html", quotes=all_quotes)


@app.route("/view/<token>")
def view_quote(token):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT q.client_name, q.address, q.job_type, q.sqft, q.demo, q.total, q.deposit,
               q.signature_name, q.signed_at, q.deposit_paid, u.company_name, u.stripe_connect_onboarded
        FROM quotes q JOIN users u ON q.user_id = u.id
        WHERE q.token = %s
    """, (token,))
    row = c.fetchone()
    conn.close()

    if row is None:
        return "Quote not found", 404

    (client_name, address, job_type, sqft, demo, total, deposit,
     signature_name, signed_at, deposit_paid, company_name, contractor_can_collect) = row

    return render_template(
        "view_quote.html",
        token=token,
        company_name=company_name,
        client_name=client_name,
        address=address,
        job_type=job_type,
        sqft=sqft,
        demo=demo,
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
    c.execute("SELECT * FROM quotes WHERE id = %s AND user_id = %s", (id, current_user.id))
    q = c.fetchone()
    c.execute("SELECT company_name FROM users WHERE id = %s", (current_user.id,))
    company_name = c.fetchone()[0]
    conn.close()

    if q is None:
        return "Quote not found", 404

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 20)
    pdf.cell(0, 15, company_name, ln=True)
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, f"Client: {q[1]}", ln=True)
    pdf.cell(0, 10, f"Address: {q[2]}", ln=True)
    pdf.cell(0, 10, f"Job Type: {q[3]}", ln=True)
    pdf.cell(0, 10, f"Square Footage: {q[4]}", ln=True)
    pdf.cell(0, 10, f"Demo: {q[5]}", ln=True)
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, f"Total: ${q[6]:,.2f}", ln=True)
    pdf.cell(0, 10, f"Deposit Due: ${q[7]:,.2f}", ln=True)

    path = f"quote_{id}.pdf"
    pdf.output(path)
    return send_file(path, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)