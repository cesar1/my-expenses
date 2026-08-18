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
