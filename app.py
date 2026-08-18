# Expense Tracker - Personal Finance CRUD App
# -----------------------------------------------
# Setup:
#   pip install flask
#
# Run:
#   python app.py
#
# Then open: http://127.0.0.1:5000

from datetime import datetime, timezone
from urllib.parse import urlparse
from flask import Flask, render_template, request, redirect, url_for
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import subprocess

app = Flask(__name__)
# Sessions need a secret key. Set SECRET_KEY in the environment for production;
# the fallback is for local development only (mirrors the FLASK_DEBUG pattern).
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-only-insecure-secret")
DB_PATH = os.path.join(os.path.dirname(__file__), "expenses.db")

CATEGORIES = ["Food", "Transport", "Entertainment", "Utilities", "Other"]

VERSION_FILE = os.path.join(os.path.dirname(__file__), "version.txt")


def get_build_version():
    """Identify the running build. Resolved once at startup, not per request.

    Checked in order: APP_VERSION in the environment, then version.txt (written
    by the deploy workflow right after it pulls, and by deploy/setup.sh on a
    fresh box), then the local git checkout. Git is deliberately last because
    gunicorn.service pins PATH to the venv, so git is not on PATH in
    production -- there the answer always comes from version.txt.
    """
    env_version = os.getenv("APP_VERSION", "").strip()
    if env_version:
        return env_version

    try:
        with open(VERSION_FILE, encoding="utf-8") as fh:
            file_version = fh.read().strip()
        if file_version:
            return file_version
    except OSError:
        pass

    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(__file__) or ".",
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
        if sha:
            return f"dev-{sha}"
    except (OSError, subprocess.SubprocessError):
        pass

    return "dev"


app.config["BUILD_VERSION"] = get_build_version()


@app.context_processor
def inject_build_version():
    """Makes {{ build_version }} available to every template (used in the footer)."""
    return {"build_version": app.config["BUILD_VERSION"]}


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


class User(UserMixin):
    def __init__(self, id, email):
        self.id = id
        self.email = email


@login_manager.user_loader
def load_user(user_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, email FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return User(row["id"], row["email"]) if row else None


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                email         TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at    TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL,
                amount    REAL NOT NULL,
                category  TEXT NOT NULL,
                date      TEXT NOT NULL,
                user_id   INTEGER
            )
        """)
        # Migrate pre-existing databases: add user_id if the column is missing.
        # SQLite leaves existing rows NULL, so old expenses become orphaned/hidden.
        columns = [c["name"] for c in conn.execute("PRAGMA table_info(expenses)")]
        if "user_id" not in columns:
            conn.execute("ALTER TABLE expenses ADD COLUMN user_id INTEGER")


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


def validate_registration_form(form):
    email = form.get("email", "").strip().lower()
    password = form.get("password", "")

    if not email or not password:
        return None, "Email and password are required."

    if "@" not in email or "." not in email:
        return None, "Please enter a valid email address."

    if len(password) < 8:
        return None, "Password must be at least 8 characters."

    with get_db() as conn:
        existing = conn.execute(
            "SELECT 1 FROM users WHERE email = ?", (email,)
        ).fetchone()
    if existing:
        return None, "An account with that email already exists."

    return {"email": email, "password": password}, None


def safe_next_url(target):
    r"""Return target only if it is a relative path on this site, else None.

    Guards the ?next= redirect after login against being pointed at another
    host (open redirect). Backslashes are rejected because some browsers
    normalize them to slashes, turning "/\evil.com" into "//evil.com".
    """
    if not target or "\\" in target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return None
    if not target.startswith("/") or target.startswith("//"):
        return None
    return target


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        data, error = validate_registration_form(request.form)
        if error:
            return render_template("register.html", error=error)

        with get_db() as conn:
            cur = conn.execute(
                "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                (
                    data["email"],
                    generate_password_hash(data["password"]),
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
            user_id = cur.lastrowid

        login_user(User(user_id, data["email"]))
        return redirect(url_for("index"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        with get_db() as conn:
            row = conn.execute(
                "SELECT id, email, password_hash FROM users WHERE email = ?", (email,)
            ).fetchone()

        if row is None or not check_password_hash(row["password_hash"], password):
            return render_template("login.html", error="Invalid email or password.")

        login_user(User(row["id"], row["email"]))
        next_url = safe_next_url(request.args.get("next"))
        return redirect(next_url or url_for("index"))

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    with get_db() as conn:
        expenses = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? ORDER BY date DESC, id DESC",
            (current_user.id,),
        ).fetchall()
        total = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = ?",
            (current_user.id,),
        ).fetchone()[0]
    return render_template("index.html", expenses=expenses, total=total, categories=CATEGORIES)


@app.route("/add", methods=["GET", "POST"])
@login_required
def add():
    if request.method == "POST":
        data, error = validate_expense_form(request.form)
        if error:
            return render_template("add.html", categories=CATEGORIES, error=error)

        with get_db() as conn:
            conn.execute(
                "INSERT INTO expenses (description, amount, category, date, user_id) VALUES (?, ?, ?, ?, ?)",
                (data["description"], data["amount"], data["category"], data["date"], current_user.id),
            )
        return redirect(url_for("index"))

    return render_template("add.html", categories=CATEGORIES)


@app.route("/edit/<int:expense_id>", methods=["GET", "POST"])
@login_required
def edit(expense_id):
    with get_db() as conn:
        expense = conn.execute(
            "SELECT * FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, current_user.id),
        ).fetchone()

    if expense is None:
        return redirect(url_for("index"))

    if request.method == "POST":
        data, error = validate_expense_form(request.form)
        if error:
            return render_template("edit.html", expense=expense, categories=CATEGORIES, error=error)

        with get_db() as conn:
            conn.execute(
                "UPDATE expenses SET description=?, amount=?, category=?, date=? WHERE id=? AND user_id=?",
                (data["description"], data["amount"], data["category"], data["date"], expense_id, current_user.id),
            )
        return redirect(url_for("index"))

    return render_template("edit.html", expense=expense, categories=CATEGORIES)


@app.route("/delete/<int:expense_id>", methods=["POST"])
@login_required
def delete(expense_id):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, current_user.id),
        )
    return redirect(url_for("index"))


if __name__ == "__main__":
    init_db()
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
