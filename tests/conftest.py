import mongomock
import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app


@pytest.fixture
def db():
    return mongomock.MongoClient()["test_db"]


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def authed_client(client, db):
    from app.auth import create_user

    user = create_user(db, "student@example.com", "password123")
    client.post("/login", data={"email": "student@example.com", "password": "password123"})
    return client, user
