"""
Pytest setup.

DATABASE_URL is pointed at an isolated test database BEFORE any app module is
imported, so running the suite never touches the demo database. The file is
deleted at session start, so every run starts from an empty schema.
"""
import os
import pathlib
import sys

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEST_DB = BACKEND_DIR / "test_traceability.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
if TEST_DB.exists():
    TEST_DB.unlink()

import pytest  # noqa: E402


def hdr(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def client():
    # Imported only after DATABASE_URL is set — app.main creates the tables.
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def users(client):
    """One account per role, registered through the public API."""
    tokens = {}
    for role in ("admin", "producer", "distributor", "retailer"):
        email = f"{role}-pytest@example.com"
        payload = {"name": f"Pytest {role}", "email": email,
                   "password": "pytest-pass", "role": role}
        res = client.post("/auth/register", json=payload)
        if res.status_code != 200:
            res = client.post("/auth/login", json={"email": email, "password": "pytest-pass"})
        assert res.status_code == 200, res.text
        tokens[role] = res.json()["access_token"]
    return tokens


@pytest.fixture
def batch(client, users):
    """A fresh in-production batch for a single test."""
    res = client.post("/batches", json={"product_name": "Pytest Juice 1L"},
                      headers=hdr(users["producer"]))
    assert res.status_code == 200, res.text
    return res.json()
