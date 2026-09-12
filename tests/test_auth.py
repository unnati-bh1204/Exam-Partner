import pytest

from app.auth import authenticate_user, create_user, hash_password, verify_password


def test_hash_and_verify_password_roundtrip():
    hashed = hash_password("correct-horse")
    assert verify_password("correct-horse", hashed)
    assert not verify_password("wrong-password", hashed)


def test_create_user_stores_hashed_password(db):
    user = create_user(db, "student@example.com", "password123")
    assert user["email"] == "student@example.com"
    assert user["password_hash"] != "password123"


def test_create_user_rejects_duplicate_email(db):
    create_user(db, "student@example.com", "password123")
    with pytest.raises(ValueError):
        create_user(db, "student@example.com", "another-password")


def test_authenticate_user_succeeds_with_correct_password(db):
    create_user(db, "student@example.com", "password123")
    user = authenticate_user(db, "student@example.com", "password123")
    assert user is not None
    assert user["email"] == "student@example.com"


def test_authenticate_user_fails_with_wrong_password(db):
    create_user(db, "student@example.com", "password123")
    assert authenticate_user(db, "student@example.com", "wrong") is None


def test_signup_then_access_protected_page(client):
    response = client.post(
        "/signup", data={"email": "student@example.com", "password": "password123"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/subjects"


def test_login_with_wrong_password_shows_error(client):
    client.post("/signup", data={"email": "student@example.com", "password": "password123"})
    client.cookies.clear()
    response = client.post("/login", data={"email": "student@example.com", "password": "wrong"})
    assert response.status_code == 400
