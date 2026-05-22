# Expense Tracker - Personal Finance CRUD App
# -----------------------------------------------
# Setup:
#   pip install flask
#
# Run:
#   python app.py
#
# Then open: http://127.0.0.1:5000

from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import os

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), "expenses.db")

CATEGORIES = ["Food", "Transport", "Entertainment", "Utilities", "Other"]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL,
                amount    REAL NOT NULL,
                category  TEXT NOT NULL,
                date      TEXT NOT NULL
            )
        """)


def validate_expense_form(form):
    description = form.get("description", "").strip()
    amount_raw = form.get("amount", "").strip()
    category = form.get("category", "").strip()
    date = form.get("date", "").strip()

    if not description or not amount_raw or not category or not date:
        return None, "All fields are required."

    try:
        amount = float(amount_raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        return None, "Amount must be a positive number."

    if category not in CATEGORIES:
        return None, "Invalid category."

    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return None, "Date must be in YYYY-MM-DD format."

    return {"description": description, "amount": amount, "category": category, "date": date}, None


@app.route("/")
def index():
    with get_db() as conn:
        expenses = conn.execute(
            "SELECT * FROM expenses ORDER BY date DESC, id DESC"
        ).fetchall()
        total = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM expenses").fetchone()[0]
    return render_template("index.html", expenses=expenses, total=total, categories=CATEGORIES)


@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        data, error = validate_expense_form(request.form)
        if error:
            return render_template("add.html", categories=CATEGORIES, error=error)

        with get_db() as conn:
            conn.execute(
                "INSERT INTO expenses (description, amount, category, date) VALUES (?, ?, ?, ?)",
                (data["description"], data["amount"], data["category"], data["date"]),
            )
        return redirect(url_for("index"))

    return render_template("add.html", categories=CATEGORIES)


@app.route("/edit/<int:expense_id>", methods=["GET", "POST"])
def edit(expense_id):
    with get_db() as conn:
        expense = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()

    if expense is None:
        return redirect(url_for("index"))

    if request.method == "POST":
        data, error = validate_expense_form(request.form)
        if error:
            return render_template("edit.html", expense=expense, categories=CATEGORIES, error=error)

        with get_db() as conn:
            conn.execute(
                "UPDATE expenses SET description=?, amount=?, category=?, date=? WHERE id=?",
                (data["description"], data["amount"], data["category"], data["date"], expense_id),
            )
        return redirect(url_for("index"))

    return render_template("edit.html", expense=expense, categories=CATEGORIES)


@app.route("/delete/<int:expense_id>", methods=["POST"])
def delete(expense_id):
    with get_db() as conn:
        conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    return redirect(url_for("index"))


if __name__ == "__main__":
    init_db()
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
