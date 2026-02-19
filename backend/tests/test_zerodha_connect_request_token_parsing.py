from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.main import app

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_CRYPTO_KEY"] = "test-zerodha-connect-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _login(username: str) -> None:
    r = client.post("/api/auth/register", json={"username": username, "password": "pass1234"})
    assert r.status_code in {201, 400}
    r2 = client.post("/api/auth/login", json={"username": username, "password": "pass1234"})
    assert r2.status_code == 200
    client.cookies.clear()
    client.cookies.update(r2.cookies)


@pytest.fixture()
def fake_kiteconnect(monkeypatch: pytest.MonkeyPatch) -> dict:
    seen: dict[str, str] = {}

    class FakeKiteConnect:
        def __init__(self, api_key: str) -> None:  # noqa: ARG002
            return None

        def generate_session(self, request_token: str, api_secret: str):  # noqa: ARG002
            seen["request_token"] = request_token
            return {"access_token": "at-1"}

        def set_access_token(self, _token: str) -> None:
            return None

        def profile(self) -> dict:
            return {"user_id": "U1"}

    sys.modules["kiteconnect"] = SimpleNamespace(KiteConnect=FakeKiteConnect)
    return seen


def test_connect_accepts_full_redirect_url(fake_kiteconnect) -> None:
    _login("zuser1")
    # Configure API key/secret.
    resp_key = client.put("/api/brokers/zerodha/secrets/api_key", json={"value": "abcdEFGHijklMNOP"})
    assert resp_key.status_code == 200
    resp_sec = client.put("/api/brokers/zerodha/secrets/api_secret", json={"value": "secret"})
    assert resp_sec.status_code == 200

    full_url = "https://example.com/callback?status=success&request_token=rt123&action=login"
    resp = client.post("/api/zerodha/connect", json={"request_token": full_url})
    assert resp.status_code == 200
    assert fake_kiteconnect["request_token"] == "rt123"


def test_connect_accepts_querystring(fake_kiteconnect) -> None:
    _login("zuser2")
    resp_key = client.put("/api/brokers/zerodha/secrets/api_key", json={"value": "abcdEFGHijklMNOP"})
    assert resp_key.status_code == 200
    resp_sec = client.put("/api/brokers/zerodha/secrets/api_secret", json={"value": "secret"})
    assert resp_sec.status_code == 200

    qs = "request_token=rt456&status=success&action=login"
    resp = client.post("/api/zerodha/connect", json={"request_token": qs})
    assert resp.status_code == 200
    assert fake_kiteconnect["request_token"] == "rt456"
