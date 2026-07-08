from flask import Flask, request, redirect, send_file
import psycopg2
from fpdf import FPDF
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta, timezone
import os
import base64
import requests
import stripe

app = Flask(__name__)
app.secret_key = 'precision2024secret'

login_manager = LoginManager(app)
login_manager.login_view = 'login'

stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_PRICE_ID = "price_1Tqmr2QKfprCRWsdLfLubmdF"
APP_URL = "https://quote-app-flfp.onrender.com"


def get_db():
    return psycopg2.connect(os.environ.get('DATABASE_URL'))


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
        now = datetime.now(timezone.utc)

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
    conn.commit()
    conn.close()


init_db()


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])
        company_name = request.form["company_name"]
        trial_end = datetime.now(timezone.utc) + timedelta(days=14)
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
            return """
             <html>
            <body style="font-family:Arial;max-width:400px;margin:50px auto">
            <h2 style="color:#E8A317">Create Account</h2>
            <p style="color:#B33A3A;background:#fdecea;padding:10px;border-radius:5px">
                That email is already registered. Please <a href="/login">log in</a> instead.
            </p>
            <form method="POST" action="/register">
                <p>Company Name:</p>
                <input type="text" name="company_name"><br><br>
                <p>Email:</p>
                <input type="text" name="email"><br><br>
                <p>Password:</p>
                <input type="password" name="password"><br><br>
                <input type="submit" value="Register">
            </form>
            <a href="/login">Already have an account? Login</a>
            </body>
            </html>
            """
        conn.close()
        return redirect("/login")
    return """
     <html>
    <body style="font-family:Arial;max-width:400px;margin:50px auto">
    <h2 style="color:#E8A317">Create Account</h2>
    <form method="POST" action="/register">
        <p>Company Name:</p>
        <input type="text" name="company_name"><br><br>
        <p>Email:</p>
        <input type="text" name="email"><br><br>
        <p>Password:</p>
        <input type="password" name="password"><br><br>
        <input type="submit" value="Register">
    </form>
    <a href="/login">Already have an account? Login</a>
    </body>
    </html>
    """


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
        return "Invalid email or password"
    return """
        <html><body style="font-family:Arial;max-width:400px;margin:50px auto">
        <h2 style="color:#E8A317">Login</h2>
        <form method="POST" action="/login">
            <label>Email:</label><br>
            <input type="text" name="email" style="width:100%;padding:10px;margin:5px 0;border:1px solid #ccc"><br>
            <label>Password:</label><br>
            <input type="password" name="password" style="width:100%;padding:10px;margin:5px 0;border:1px solid #ccc"><br>
            <button type="submit" style="background:#E8A317;color:white;padding:10px;border:none;width:100%;margin-top:10px;font-size:16px;cursor:pointer">Login</button>
            </form>
            <a href="/register">Don't have an account? Register</a>
            </body></html>
    """


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

    now = datetime.now(timezone.utc)
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

    button_html = '<a href="/subscribe" style="display:block;text-align:center;background:#E8A317;color:white;padding:12px;border-radius:5px;text-decoration:none;margin-top:15px;">Subscribe Now</a>' if show_button else ''

    return f"""
    <html>
    <body style="font-family:Arial;max-width:400px;margin:50px auto">
        <h2 style="color:#E8A317">Billing</h2>
        <p>{message}</p>
        {button_html}
        <a href="/" style="display:block;text-align:center; margin-top:15px; color:#0E0E0E;">Back to Home</a>
        <a href="/logout" style="display:block;text-align:center; margin-top:10px; color:#B33A3A;">Logout</a>
    </body>
    </html>
    """


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
        user_id = session_obj.get("client_reference_id")
        customer_id = session_obj.get("customer")
        subscription_id = session_obj.get("subscription")
        if user_id:
            c.execute(
                "UPDATE users SET stripe_customer_id = %s, stripe_subscription_id = %s, subscription_status = 'active' WHERE id = %s",
                (customer_id, subscription_id, user_id)
            )
            conn.commit()

    elif event["type"] == "customer.subscription.updated":
        sub = event["data"]["object"]
        customer_id = sub.get("customer")
        status = sub.get("status")
        c.execute(
            "UPDATE users SET subscription_status = %s WHERE stripe_customer_id = %s",
            (status, customer_id)
        )
        conn.commit()

    elif event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        customer_id = sub.get("customer")
        c.execute(
            "UPDATE users SET subscription_status = 'canceled' WHERE stripe_customer_id = %s",
            (customer_id,)
        )
        conn.commit()

    conn.close()
    return "", 200


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

    c.execute("SELECT company_name, price_driveway, price_patio, price_foundation, demo_upcharge FROM users WHERE id = %s", (current_user.id,))
    user_data = c.fetchone()
    conn.close()

    company_name, price_driveway, price_patio, price_foundation, demo_upcharge = user_data

    return f"""
    <html>
    <body style="font-family:Arial;max-width:400px;margin:50px auto">
        <h2 style="color:#E8A317">Settings</h2>
        <form method="POST" action="/settings">
            <label>Company Name:</label><br>
            <input type="text" name="company_name" value="{company_name}" style="width:100%;padding:10px;margin:5px 0;border:1px solid #ccc"><br>
            <label>Driveway price per sqft ($):</label><br>
            <input type="number" step="0.01" name="price_driveway" value="{price_driveway}" style="width:100%;padding:10px;margin:5px 0;border:1px solid #ccc"><br>
            <label>Patio price per sqft ($):</label><br>
            <input type="number" step="0.01" name="price_patio" value="{price_patio}" style="width:100%;padding:10px;margin:5px 0;border:1px solid #ccc"><br>
            <label>Foundation price per sqft ($):</label><br>
            <input type="number" step="0.01" name="price_foundation" value="{price_foundation}" style="width:100%;padding:10px;margin:5px 0;border:1px solid #ccc"><br>
            <label>Demo upcharge per sqft ($):</label><br>
            <input type="number" step="0.01" name="demo_upcharge" value="{demo_upcharge}" style="width:100%;padding:10px;margin:5px 0;border:1px solid #ccc"><br>
            <button type="submit" style="background:#E8A317;color:white;padding:10px;border:none;width:100%;margin-top:10px;font-size:16px;cursor:pointer">Save</button>
        </form>
        <a href="/" style="display:block;text-align:center; margin-top:15px; color:#0E0E0E;">Back to Home</a>
    </body>
    </html>
    """


@app.route("/")
@login_required
@subscription_required
def home():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT company_name FROM users WHERE id = %s", (current_user.id,))
    company_name = c.fetchone()[0]
    conn.close()

    return f"""
    <html>
    <head>
        <title>{company_name}</title>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; background-color: #f5f5f5; }}
            h1 {{ color: #E8A317; border-bottom: 3px solid #E8A317; padding-bottom: 10px; }}
            input, select {{ width: 100%; padding: 10px; margin: 8px 0; border: 1px solid #ccc; border-radius: 5px; font-size: 16px; }}
            button {{ background-color: #E8A317; color: white; padding: 12px 30px; border: none; border-radius: 5px; font-size: 18px; cursor: pointer; width: 100%; margin-top: 10px; }}
            label {{ font-weight: bold; color: #333; }}
        </style>
    </head>
    <body>
        <h1>{company_name} Quote Generator</h1>
        <form method="POST" action="/quote">
            <label>Client Name:</label>
            <input type="text" name="client_name">
            <label>Client Email:</label>
            <input type="email" name="client_email">
            <label>Address:</label>
            <input type="text" name="address">
            <label>Square Footage:</label>
            <input type="number" name="sqft">
            <label>Job Type:</label>
            <select name="job_type">
                <option value="driveway">Driveway</option>
                <option value="patio">Patio</option>
                <option value="foundation">Foundation</option>
            </select>
            <label>Demo needed?</label>
            <select name="demo">
                <option value="yes">Yes</option>
                <option value="no">No</option>
            </select>
            <button type="submit">Generate Quote</button>
            <a href="/quotes" style="display:block;text-align:center; margin-top:15px; color:#0E0E0E;">View All Quotes</a>
            <a href="/settings" style="display:block;text-align:center; margin-top:10px; color:#0E0E0E;">Settings</a>
            <a href="/billing" style="display:block;text-align:center; margin-top:10px; color:#0E0E0E;">Billing</a>
            <a href="/logout" style="display:block;text-align:center; margin-top:10px; color:#B33A3A;">Logout</a>
        </form>
    </body>
    </html>
    """


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
    c.execute("INSERT INTO quotes (client_name, address, job_type, sqft, demo, total, deposit, client_email, user_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
              (client_name, address, job_type, sqft, demo, total, deposit, client_email, current_user.id))
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
        f"Hi {client_name},\n\nPlease find your quote attached.\n\nTotal: ${total:,.2f}\nDeposit Due: ${deposit:,.2f}\n\nThank you,\n{company_name}",
        pdf_base64,
        f"quote_{client_name}.pdf"
    )

    send_email(
        current_user.email,
        f"New lead: {client_name}",
        f"You just generated a new quote.\n\nClient: {client_name}\nEmail: {client_email}\nAddress: {address}\nJob Type: {job_type}\nSquare Footage: {sqft}\nDemo: {demo}\nTotal: ${total:,.2f}\nDeposit Due: ${deposit:,.2f}"
    )

    return f"""
    <html>
    <head>
        <title>Quote Summary</title>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; background-color: #f5f5f5; }}
            h1 {{ color: #E8A317; border-bottom: 3px solid #E8A317; padding-bottom: 10px; }}
            .quote-box {{ background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            p {{ font-size: 18px; margin: 10px 0; }}
            .total {{ font-size: 24px; font-weight: bold; color: #E8A317; }}
            a {{ display: block; text-align: center; margin-top: 20px; background-color: #0E0E0E; color: white; padding: 12px; border-radius: 5px; text-decoration: none; }}
        </style>
    </head>
    <body>
        <h1>Quote Summary</h1>
        <div class="quote-box">
            <p>Client: {client_name}</p>
            <p>Address: {address}</p>
            <p>Job Type: {job_type}</p>
            <p>Square Footage: {sqft}</p>
            <p>Demo: {demo}</p>
            <p class="total">Total: ${total}</p>
            <p>Deposit Due: ${deposit}</p>
        </div>
        <a href="/">Generate Another Quote</a>
    </body>
    </html>
    """


@app.route("/quotes")
@login_required
@subscription_required
def view_quotes():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM quotes WHERE user_id = %s", (current_user.id,))
    all_quotes = c.fetchall()
    conn.close()

    rows = ""
    for q in all_quotes:
        rows += f"""
        <tr>
            <td>{q[0]}</td>
            <td>{q[1]}</td>
            <td>{q[2]}</td>
            <td>{q[3]}</td>
            <td>{q[4]}</td>
            <td>{q[5]}</td>
            <td>${q[6]:,.2f}</td>
            <td>${q[7]:,.2f}</td>
            <td><a href="/pdf/{q[0]}">PDF</a> | <a href="/delete/{q[0]}">Delete</a></td>
        </tr>
        """

    return f"""
    <html>
    <head>
        <title>All Quotes</title>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 900px; margin: 50px auto; background-color: #f5f5f5; }}
            h1 {{ color: #E8A317; }}
            table {{ width: 100%; border-collapse: collapse; background: white; }}
            th, td {{ padding: 10px; border: 1px solid #ddd; text-align: left; }}
            th {{ background-color: #0E0E0E; color: white; }}
            a {{ display: inline-block; margin-top: 20px; color: #E8A317; }}
        </style>
    </head>
    <body>
        <h1>All Quotes</h1>
        <table>
            <tr>
                <th>ID</th><th>Client</th><th>Address</th><th>Job Type</th><th>Sqft</th><th>Demo</th><th>Total</th><th>Deposit</th>
            </tr>
            {rows}
        </table>
        <a href="/">Back to Home</a>
        <a href="/logout" style="display:block;text-align:center; margin-top:10px; color:#B33A3A;">Logout</a>
    </body>
    </html>
    """


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