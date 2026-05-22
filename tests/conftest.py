import pytest
import app as flask_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(flask_app, "DB_PATH", str(tmp_path / "test.db"))
    flask_app.app.config["TESTING"] = True
    flask_app.init_db()
    with flask_app.app.test_client() as c:
        yield c


@pytest.fixture
def seeded_client(client):
    """Client with one expense already in the DB."""
    client.post("/add", data={
        "description": "Coffee",
        "amount": "4.50",
        "category": "Food",
        "date": "2024-01-15",
    })
    return client
