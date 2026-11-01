"""Tests run against a real PostgreSQL with pgvector (set TEST_DATABASE_URL).

Each test starts from empty tables. External services (Groq, embeddings, PDF downloads)
are replaced by fakes in the tests that need them.
"""
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://ai:ai@127.0.0.1:5432/ai")
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("GROQ_API_KEY", "test-key")
os.environ.setdefault("REQUEST_LIMIT", "25")


def _reset_modules() -> None:
    from app import config, db, deps, repository
    config.get_settings.cache_clear()
    db.get_engine.cache_clear()
    deps._throttle = None
    repository._schema_ready = False


@pytest.fixture(autouse=True)
def fresh_database():
    _reset_modules()
    from app import db, repository
    with db.get_engine().begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS messages, conversations, sessions, documents, users, request_quota CASCADE"))
    repository.ensure_schema()
    yield
    _reset_modules()


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture
def signed_up(client):
    """Creates a user and returns (headers, user_json)."""
    def _make(email: str = "ada@example.com", password: str = "correct-horse"):
        response = client.post("/api/auth/signup", json={"email": email, "password": password})
        assert response.status_code == 201, response.text
        body = response.json()
        return {"Authorization": f"Bearer {body['token']}"}, body["user"]
    return _make
