import app as flask_app

VALID_EXPENSE = {
    "description": "Coffee",
    "amount": "4.50",
    "category": "Food",
    "date": "2024-01-15",
}


# ── Index ──────────────────────────────────────────────────────────────────


def test_index_empty(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_index_shows_expense(seeded_client):
    resp = seeded_client.get("/")
    assert b"Coffee" in resp.data
    assert b"4.50" in resp.data


# ── Add ────────────────────────────────────────────────────────────────────


def test_add_get(client):
    resp = client.get("/add")
    assert resp.status_code == 200


def test_add_valid(client):
    resp = client.post("/add", data=VALID_EXPENSE)
    assert resp.status_code == 302
    assert client.get("/").data.count(b"Coffee") == 1


def test_add_missing_field(client):
    resp = client.post("/add", data={**VALID_EXPENSE, "amount": ""})
    assert resp.status_code == 200
    assert b"All fields are required" in resp.data


def test_add_invalid_amount(client):
    resp = client.post("/add", data={**VALID_EXPENSE, "amount": "abc"})
    assert b"Amount must be a positive number" in resp.data


def test_add_invalid_category(client):
    resp = client.post("/add", data={**VALID_EXPENSE, "category": "Vacation"})
    assert b"Invalid category" in resp.data


def test_add_invalid_date(client):
    resp = client.post("/add", data={**VALID_EXPENSE, "date": "01/15/2024"})
    assert b"Date must be in YYYY-MM-DD format" in resp.data


# ── Edit ───────────────────────────────────────────────────────────────────


def test_edit_get(seeded_client):
    resp = seeded_client.get("/edit/1")
    assert resp.status_code == 200
    assert b"Coffee" in resp.data


def test_edit_nonexistent_redirects(client):
    resp = client.get("/edit/999")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/"


def test_edit_valid(seeded_client):
    resp = seeded_client.post("/edit/1", data={
        "description": "Espresso",
        "amount": "3.00",
        "category": "Food",
        "date": "2024-01-16",
    })
    assert resp.status_code == 302
    index = seeded_client.get("/")
    assert b"Espresso" in index.data
    assert b"Coffee" not in index.data


def test_edit_invalid_amount(seeded_client):
    resp = seeded_client.post("/edit/1", data={**VALID_EXPENSE, "amount": "-1"})
    assert b"Amount must be a positive number" in resp.data


# ── Delete ─────────────────────────────────────────────────────────────────


def test_delete(seeded_client):
    resp = seeded_client.post("/delete/1")
    assert resp.status_code == 302
    assert b"Coffee" not in seeded_client.get("/").data


def test_delete_nonexistent(client):
    resp = client.post("/delete/999")
    assert resp.status_code == 302


# ── Version footer ─────────────────────────────────────────────────────────


def test_footer_shows_build_version(client, monkeypatch):
    monkeypatch.setitem(flask_app.app.config, "BUILD_VERSION", "v42 (abc1234)")
    assert b"build <code>v42 (abc1234)</code>" in client.get("/").data


def test_footer_shows_on_logged_out_pages(anon_client, monkeypatch):
    monkeypatch.setitem(flask_app.app.config, "BUILD_VERSION", "v42 (abc1234)")
    assert b"v42 (abc1234)" in anon_client.get("/login").data


# ── Landing page (logged out) ──────────────────────────────────────────────


def test_landing_shows_sample_expenses(anon_client):
    resp = anon_client.get("/")
    assert resp.status_code == 200
    for text in (b"Rent", b"Mortgage", b"Groceries", b"Netflix", b"Sign Up"):
        assert text in resp.data


def test_landing_samples_are_read_only(anon_client):
    # No edit/delete controls on the preview -- nothing that dead-ends at /login.
    resp = anon_client.get("/")
    assert b"bi-pencil" not in resp.data
    assert b"bi-trash" not in resp.data


def test_landing_samples_not_in_database(anon_client):
    anon_client.get("/")
    anon_client.post("/register", data={"email": "fresh@example.com", "password": "password123"})
    # A brand new user still sees the empty state; no sample leaked into SQLite.
    assert b"No expenses yet" in anon_client.get("/").data


def test_logged_in_user_sees_no_samples(client):
    assert b"Mortgage" not in client.get("/").data


def test_sample_dates_are_current_month(anon_client):
    from datetime import datetime

    month = datetime.now().strftime("%Y-%m").encode()
    resp = anon_client.get("/")
    assert resp.data.count(month) == len(flask_app.SAMPLE_EXPENSES)


def test_landing_total_matches_rows(anon_client):
    expected = sum(row["amount"] for row in flask_app.SAMPLE_EXPENSES)
    assert f"${expected:.2f}".encode() in anon_client.get("/").data


def test_sample_categories_are_all_valid(anon_client):
    # Guards the CLAUDE.md convention: CATEGORIES is the single source of truth.
    for row in flask_app.SAMPLE_EXPENSES:
        assert row["category"] in flask_app.CATEGORIES


# ── Housing category ───────────────────────────────────────────────────────


def test_housing_category_accepted(client):
    client.post("/add", data={**VALID_EXPENSE, "description": "Rent", "category": "Housing"})
    resp = client.get("/")
    assert b"cat-Housing" in resp.data
    assert b"Rent" in resp.data


def test_healthz_ok(anon_client):
    resp = anon_client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_healthz_reports_error_when_db_unreachable(anon_client, monkeypatch):
    """The gate must fail when SQLite is unreachable -- that is the whole point
    of probing /healthz instead of /login during a deploy."""
    monkeypatch.setattr(flask_app, "DB_PATH", "/nonexistent/dir/expenses.db")
    resp = anon_client.get("/healthz")
    assert resp.status_code == 503
    assert resp.get_json()["status"] == "error"
