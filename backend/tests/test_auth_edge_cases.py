"""Token-validation and signup/login edge cases for the auth surface.

Complements test_auth.py, which covers the happy path plus obvious
failures. Everything here still goes through the real endpoints - tokens
are forged with the app's own signing helpers only where the test is
specifically about rejecting a malformed/expired/foreign token.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.db import SessionLocal
from app.main import app
from app.models.user import User
from app.services.auth import ALGORITHM, SECRET_KEY, verify_password

client = TestClient(app)

# A second client that returns the 500 response instead of re-raising the
# server-side exception, so a bug in error handling is reported as a
# failed assertion ("expected 401, got 500") rather than an opaque raise.
client_without_raise = TestClient(app, raise_server_exceptions=False)

TEST_PASSWORD = "TestPassword123!"


def unique_email() -> str:
    return f"test-{uuid.uuid4().hex[:8]}@example.com"


@pytest.fixture
def account():
    """A signed-up, logged-in user plus the DB id behind the token."""
    email = unique_email()
    signup = client.post(
        "/auth/signup", json={"email": email, "password": TEST_PASSWORD}
    )
    assert signup.status_code == 201

    login = client.post(
        "/auth/login", json={"email": email, "password": TEST_PASSWORD}
    )
    token = login.json()["access_token"]

    db = SessionLocal()
    user_id = db.query(User).filter(User.email == email).first().id
    db.close()

    yield {
        "email": email,
        "password": TEST_PASSWORD,
        "token": token,
        "user_id": user_id,
    }

    db = SessionLocal()
    db.query(User).filter(User.email == email).delete()
    db.commit()
    db.close()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _forge_token(claims: dict, secret: str = SECRET_KEY) -> str:
    return jwt.encode(claims, secret, algorithm=ALGORITHM)


# ============================================================
# Signup / login request validation
# ============================================================


def test_signup_rejects_invalid_email():
    response = client.post(
        "/auth/signup", json={"email": "not-an-email", "password": TEST_PASSWORD}
    )

    assert response.status_code == 422


def test_signup_requires_password():
    response = client.post("/auth/signup", json={"email": unique_email()})

    assert response.status_code == 422


def test_login_requires_password(account):
    response = client.post("/auth/login", json={"email": account["email"]})

    assert response.status_code == 422


def test_signup_stores_a_verifiable_hash_not_the_plaintext(account):
    db = SessionLocal()
    stored = (
        db.query(User)
        .filter(User.email == account["email"])
        .first()
        .hashed_password
    )
    db.close()

    assert stored != account["password"]
    assert account["password"] not in stored
    # The stored hash must still be usable to verify the real password.
    assert verify_password(account["password"], stored) is True


# ============================================================
# Token validation in GET /auth/me
# ============================================================


def test_me_rejects_expired_token(account):
    expired = _forge_token(
        {
            "sub": str(account["user_id"]),
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        }
    )

    response = client.get("/auth/me", headers=_auth(expired))

    assert response.status_code == 401


def test_me_rejects_token_signed_with_a_different_secret(account):
    forged = _forge_token(
        {"sub": str(account["user_id"])}, secret="definitely-not-the-real-secret"
    )

    response = client.get("/auth/me", headers=_auth(forged))

    assert response.status_code == 401


def test_me_rejects_token_whose_user_was_deleted(account):
    db = SessionLocal()
    db.query(User).filter(User.id == account["user_id"]).delete()
    db.commit()
    db.close()

    response = client.get("/auth/me", headers=_auth(account["token"]))

    assert response.status_code == 401


def test_me_rejects_empty_bearer_token():
    response = client.get("/auth/me", headers={"Authorization": "Bearer "})

    assert response.status_code == 401


def test_me_rejects_signed_token_with_non_numeric_subject(account):
    """A correctly signed token whose "sub" isn't a user id should be
    treated as invalid credentials (401), not blow up while resolving the
    user. Only someone holding SECRET_KEY can mint such a token, but a
    500 here is still an unhandled error on an auth path.
    """
    forged = _forge_token({"sub": "not-a-user-id"})

    response = client_without_raise.get("/auth/me", headers=_auth(forged))

    assert response.status_code == 401
