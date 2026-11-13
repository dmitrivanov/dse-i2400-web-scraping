import pytest
from fastapi.testclient import TestClient
from mysql.connector import Error

from main import app
import db

client = TestClient(app)


def test_welcome():
    response = client.get("/")
    assert response.status_code == 200
    assert "MY_CUSTOM_BOT" in response.json()["message"]


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_database_health(monkeypatch):
    monkeypatch.setattr(db, "get_table_names", lambda: ["search_queries"])
    response = client.get("/db-health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "tables": ["search_queries"]}


@pytest.mark.parametrize("error", [Error("secret-password"), ValueError("secret-password")])
def test_database_failure(monkeypatch, error):
    def fail():
        raise error
    monkeypatch.setattr(db, "get_table_names", fail)
    response = client.get("/db-health")
    assert response.status_code == 503
    assert "secret-password" not in response.text
