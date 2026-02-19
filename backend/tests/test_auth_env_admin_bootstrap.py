from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import User

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    # Note: app.core.config.get_settings intentionally clears ST_ADMIN_* during
    # pytest runs so admin-protected APIs stay accessible without credentials.
    # For these auth tests we override the dependency to simulate a real runtime
    # environment where ST_ADMIN_USERNAME/PASSWORD are configured.
    app.dependency_overrides[get_settings] = lambda: Settings(
        crypto_key="test-auth-env-admin-secret",
        admin_username="admin",
        admin_password="admin-pass",
        environment="dev",
        debug=True,
    )
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Ensure no stale cached settings leak in from other tests.
    get_settings.cache_clear()


def teardown_module() -> None:  # type: ignore[override]
    app.dependency_overrides.pop(get_settings, None)
    get_settings.cache_clear()


def test_env_admin_login_bootstraps_admin_user() -> None:
    resp = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin-pass"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "admin"
    assert body["role"] == "ADMIN"
    assert "st_session" in resp.cookies

    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "admin").one_or_none()
        assert user is not None
        assert user.role == "ADMIN"


def test_env_admin_login_rejects_wrong_password() -> None:
    resp = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong"},
    )
    assert resp.status_code == 401


def test_session_cookie_secure_respects_forwarded_proto() -> None:
    resp = client.post(
        "/api/auth/login",
        headers={"x-forwarded-proto": "https"},
        json={"username": "admin", "password": "admin-pass"},
    )
    assert resp.status_code == 200
    set_cookie = resp.headers.get("set-cookie", "")
    assert "Secure" in set_cookie
