import pytest
import app as flask_app


@pytest.fixture
def anon_client(tmp_path, monkeypatch):
    """A client with a fresh DB and no logged-in user."""
    monkeypatch.setattr(flask_app, "DB_PATH", str(tmp_path / "test.db"))
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["SECRET_KEY"] = "test-secret"
    flask_app.init_db()
    with flask_app.app.test_client() as c:
        yield c


def register_and_login(client, email="user@example.com", password="password123"):
    """Register a user and leave them logged in. Returns (email, password)."""
    client.post("/register", data={"email": email, "password": password})
    return email, password


@pytest.fixture
def client(anon_client):
    """Client with a registered, logged-in user (registration auto-logs in)."""
    register_and_login(anon_client)
    return anon_client


@pytest.fixture
def seeded_client(client):
    """Client with one expense already in the DB, owned by the logged-in user."""
    client.post("/add", data={
        "description": "Coffee",
        "amount": "4.50",
        "category": "Food",
        "date": "2024-01-15",
    })
    return client
