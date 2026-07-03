from flask import Flask, request, redirect, send_file
import sqlite3
from fpdf import FPDF 
from flask_mail import Mail, Message
app = Flask(__name__)
app.config['MAIL_SERVER'] = 'precisionconcreteinc.net'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USERNAME'] = 'estimates@precisionconcreteinc.net'
app.config['MAIL_PASSWORD'] = 'Gunnerhorse15'
mail = Mail(app)

def init_db():
    conn = sqlite3.connect("quotes.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY,
            client_name TEXT,
            address TEXT,
            job_type TEXT,
            sqft INTEGER,
            demo TEXT,
            total REAL,
            deposit REAL,
                        client_email TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()            


@app.route("/")
def home():
    return """
    <html>
    <head>
        <title>Precision Concrete</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; background-color: #f5f5f5; }
            h1 { color: #E8A317; border-bottom: 3px solid #E8A317; padding-bottom: 10px; }
            input, select { width: 100%; padding: 10px; margin: 8px 0; border: 1px solid #ccc; border-radius: 5px; font-size: 16px; }
            button { background-color: #E8A317; color: white; padding: 12px 30px; border: none; border-radius: 5px; font-size: 18px; cursor: pointer; width: 100%; margin-top: 10px; }
            label { font-weight: bold; color: #333; }
        </style>
    </head>
    <body>
        <h1>Precision Concrete Quote Generator</h1>
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
        </form>
    </body>
    </html>
    """

@app.route("/quote", methods=["POST"])
def quote():
    client_name = request.form["client_name"]
    client_email = request.form["client_email"]
    address = request.form["address"]
    sqft = int(request.form["sqft"])
    job_type = request.form["job_type"]
    demo = request.form["demo"]

    if job_type == "driveway":
        price_per_sqft = 25
    elif job_type == "patio":
        price_per_sqft = 22
    else:
        price_per_sqft = 28

    if demo == "yes":
        price_per_sqft += 7

    total = price_per_sqft * sqft
    deposit = min(1000, total * 0.10)

    conn = sqlite3.connect("quotes.db")
    c = conn.cursor()
    c.execute("INSERT INTO quotes (client_name, address, job_type, sqft, demo, total, deposit, client_email) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (client_name, address, job_type, sqft, demo, total, deposit, client_email))
    conn.commit()
    conn.close()
    path = f"quote_{client_name}.pdf"
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 20)
    pdf.cell(0, 15, "Precision Concrete Inc.", ln=True)
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
                  
    msg = Message(

        subject="Your Quote from Precision Concrete Inc.",
        sender="estimates@precisionconcreteinc.net",
        recipients=[client_email]

    )
    msg.body = f"Hi {client_name},\n\nPlease find your quote attached.\n\nTotal: ${total:,.2f}\nDeposit Due: ${deposit:,.2f}\n\n\Thank you,\nPrecision Concrete Inc."
    with open(path, "rb") as f:
        msg.attach(f"quote_{client_name}.pdf", "application/pdf", f.read())
    try:
        mail.send(msg)
    except Exception as e:
        print(f"Email error: {e}")       
        

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
def view_quotes():
    conn = sqlite3.connect("quotes.db")
    c = conn.cursor()
    c.execute("SELECT * FROM quotes")
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
            <td><a href="/pdf/{q[0]}",>PDF</a> | <a href="/delete/{q[0]}">Delete</a></td>

           
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
    </body>
    </html>
    """
@app.route("/delete/<int:id>")
def delete_quote(id):
    conn = sqlite3.connect("quotes.db")
    c = conn.cursor()
    c.execute("Delete FROM quotes WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect("/quotes")
@app.route("/pdf/<int:id>")
def generate_pdf(id):
    conn = sqlite3.connect("quotes.db")
    c = conn.cursor()
    c.execute("SELECT * FROM quotes WHERE id = ?", (id,))
    q = c.fetchone()
    conn.close()

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B",20)
    pdf.cell(0, 15, "Precision Concrete Inc.", ln=True)
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, f"Client: {q[1]}", ln=True)
    pdf.cell(0, 10, f"Address: {q[2]}", ln=True)
    pdf.cell(0, 10, f"Job Type: {q[3]}", ln=True)
    pdf.cell(0, 10, f"Square Footage: {q[4]}", ln=True)
    pdf.cell(0, 10, f"Demo: {q[5]}", ln=True)
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, f"Total: ${q[6]}:,.2f)", ln=True)
    pdf.cell (90, 10, f"Deposit Due: ${q[7]:,.2f}", ln=True)

    path = f"quote_{id}.pdf"
    pdf.output(path)
    return send_file(path, as_attachment=True)

    
if __name__ == "__main__":
    app.run(debug=True)