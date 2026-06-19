from conftest import register_and_login


# ── Registration ─────────────────────────────────────────────────────────────


def test_register_logs_in(anon_client):
    resp = anon_client.post("/register", data={
        "email": "new@example.com",
        "password": "password123",
    })
    assert resp.status_code == 302
    # Now logged in: index is reachable instead of redirecting to /login.
    assert anon_client.get("/").status_code == 200


def test_register_duplicate_email(anon_client):
    register_and_login(anon_client, email="dupe@example.com")
    resp = anon_client.post("/register", data={
        "email": "dupe@example.com",
        "password": "password123",
    })
    assert b"already exists" in resp.data


def test_register_invalid_email(anon_client):
    resp = anon_client.post("/register", data={
        "email": "notanemail",
        "password": "password123",
    })
    assert b"valid email" in resp.data


def test_register_short_password(anon_client):
    resp = anon_client.post("/register", data={
        "email": "short@example.com",
        "password": "short",
    })
    assert b"at least 8 characters" in resp.data


# ── Login / Logout ───────────────────────────────────────────────────────────


def test_login_valid(anon_client):
    register_and_login(anon_client, email="login@example.com", password="password123")
    anon_client.post("/logout")
    resp = anon_client.post("/login", data={
        "email": "login@example.com",
        "password": "password123",
    })
    assert resp.status_code == 302
    assert anon_client.get("/").status_code == 200


def test_login_wrong_password(anon_client):
    register_and_login(anon_client, email="login2@example.com", password="password123")
    anon_client.post("/logout")
    resp = anon_client.post("/login", data={
        "email": "login2@example.com",
        "password": "wrongpassword",
    })
    assert b"Invalid email or password" in resp.data


def test_logout(client):
    assert client.get("/").status_code == 200
    client.post("/logout")
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


# ── Protected routes ─────────────────────────────────────────────────────────


def test_protected_routes_redirect_when_logged_out(anon_client):
    for path in ("/", "/add", "/edit/1"):
        resp = anon_client.get(path)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


# ── Per-user isolation ───────────────────────────────────────────────────────


def test_users_cannot_see_each_others_expenses(anon_client):
    # User A creates an expense.
    register_and_login(anon_client, email="a@example.com")
    anon_client.post("/add", data={
        "description": "A-secret-coffee",
        "amount": "4.50",
        "category": "Food",
        "date": "2024-01-15",
    })
    anon_client.post("/logout")

    # User B should not see it, and editing A's id should redirect away.
    register_and_login(anon_client, email="b@example.com")
    index = anon_client.get("/")
    assert b"A-secret-coffee" not in index.data

    edit_resp = anon_client.get("/edit/1")
    assert edit_resp.status_code == 302
    assert edit_resp.headers["Location"] == "/"


def test_user_cannot_delete_others_expense(anon_client):
    register_and_login(anon_client, email="owner@example.com")
    anon_client.post("/add", data={
        "description": "Owned",
        "amount": "9.00",
        "category": "Food",
        "date": "2024-01-15",
    })
    anon_client.post("/logout")

    register_and_login(anon_client, email="attacker@example.com")
    anon_client.post("/delete/1")  # attempt to delete owner's expense
    anon_client.post("/logout")

    # Owner still sees their expense.
    anon_client.post("/login", data={"email": "owner@example.com", "password": "password123"})
    assert b"Owned" in anon_client.get("/").data
