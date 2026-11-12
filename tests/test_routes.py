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


def test_landing_shows_streaming_prices(anon_client):
    resp = anon_client.get("/")
    assert resp.status_code == 200
    assert b"Sign Up" in resp.data
    assert b"What video streaming costs" in resp.data
    assert b"What music streaming costs" in resp.data
    for service in flask_app.STREAMING_PRICES + flask_app.MUSIC_PRICES:
        assert service["service"].encode() in resp.data
        for plan in service["plans"]:
            assert f"${plan['price']:.2f}".encode() in resp.data


def test_landing_is_read_only(anon_client):
    # No edit/delete controls on the price list -- nothing that dead-ends at /login.
    resp = anon_client.get("/")
    assert b"bi-pencil" not in resp.data
    assert b"bi-trash" not in resp.data


def test_landing_prices_not_in_database(anon_client):
    anon_client.get("/")
    anon_client.post("/register", data={"email": "fresh@example.com", "password": "password123"})
    # A brand new user still sees the empty state; no price row leaked into SQLite.
    assert b"No expenses yet" in anon_client.get("/").data


def test_logged_in_user_sees_no_price_list(client):
    data = client.get("/").data
    assert b"What video streaming costs" not in data
    assert b"What music streaming costs" not in data


def test_cards_show_the_lowest_price_on_each_list():
    for services in (flask_app.STREAMING_PRICES, flask_app.MUSIC_PRICES):
        prices = [p["price"] for s in services for p in s["plans"]]
        assert flask_app.cheapest_plan(services) == min(prices)


def test_landing_has_a_plans_start_at_card_per_list(anon_client):
    assert anon_client.get("/").data.count(b"Plans start at") == 2


def test_landing_shows_as_of_date(anon_client):
    from datetime import datetime

    # Also fails loudly if the constant is not a real YYYY-MM-DD date.
    as_of = datetime.strptime(flask_app.STREAMING_PRICES_AS_OF, "%Y-%m-%d")
    expected = f"{as_of.strftime('%B')} {as_of.day}, {as_of.year}"
    assert expected.encode() in anon_client.get("/").data


def test_streaming_prices_are_well_formed():
    # Guards a bad paste from scripts/refresh_streaming_prices.py: an empty list
    # would crash the cheapest-plan lookup and take the landing page down.
    everything = flask_app.STREAMING_PRICES + flask_app.MUSIC_PRICES
    names = [service["service"] for service in everything]
    assert flask_app.STREAMING_PRICES and flask_app.MUSIC_PRICES
    assert len(names) == len(set(names))
    for service in everything:
        assert service["url"].startswith("https://")
        assert service["plans"]
        for plan in service["plans"]:
            assert plan["name"]
            assert 0 < plan["price"] < 100


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
