from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import User

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_CRYPTO_KEY"] = "test-auth-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_register_and_login_creates_session_cookie() -> None:
    # Register a new user
    resp_register = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "secret123", "display_name": "Alice"},
    )
    assert resp_register.status_code == 201
    data = resp_register.json()
    assert data["username"] == "alice"
    assert data["role"] == "TRADER"

    # Login with the same credentials
    resp_login = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "secret123"},
    )
    assert resp_login.status_code == 200
    assert resp_login.json()["username"] == "alice"

    # Session cookie should be present and usable via the client cookie jar.
    cookies = resp_login.cookies
    assert "st_session" in cookies
    client.cookies.clear()
    client.cookies.update(cookies)

    # /me should return the current user when the cookie is attached
    resp_me = client.get("/api/auth/me")
    assert resp_me.status_code == 200
    me = resp_me.json()
    assert me["username"] == "alice"


def test_change_password_and_relogin() -> None:
    # Register and login a user
    resp_register = client.post(
        "/api/auth/register",
        json={"username": "bob", "password": "start123", "display_name": "Bob"},
    )
    assert resp_register.status_code == 201

    resp_login = client.post(
        "/api/auth/login",
        json={"username": "bob", "password": "start123"},
    )
    assert resp_login.status_code == 200
    client.cookies.clear()
    client.cookies.update(resp_login.cookies)

    # Change password
    resp_change = client.post(
        "/api/auth/change-password",
        json={"current_password": "start123", "new_password": "newpass456"},
    )
    assert resp_change.status_code == 204

    # Old password should fail
    resp_old = client.post(
        "/api/auth/login",
        json={"username": "bob", "password": "start123"},
    )
    assert resp_old.status_code == 401

    # New password should succeed
    resp_new = client.post(
        "/api/auth/login",
        json={"username": "bob", "password": "newpass456"},
    )
    assert resp_new.status_code == 200


def test_default_admin_can_be_created_via_model() -> None:
    # This test does not rely on the Alembic migration; instead it ensures that
    # the User model can represent an ADMIN user record correctly.
    with SessionLocal() as session:
        admin = User(
            username="admin-model-test",
            password_hash="dummy",
            role="ADMIN",
            display_name="Admin Test",
        )
        session.add(admin)
        session.commit()
        session.refresh(admin)
        assert admin.id is not None
        assert admin.role == "ADMIN"
