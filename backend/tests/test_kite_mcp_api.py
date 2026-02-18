from __future__ import annotations

import os
import urllib.parse

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import BrokerSecret

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_KITE_MCP_ENABLED"] = "0"
    os.environ["ST_CRYPTO_KEY"] = "test-kite-mcp-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _enable_kite_mcp() -> None:
    resp = client.put(
        "/api/settings/ai",
        json={
            "feature_flags": {"kite_mcp_enabled": True},
            "kite_mcp": {"server_url": "https://mcp.kite.trade/sse"},
        },
    )
    assert resp.status_code == 200


@pytest.fixture()
def fake_kite_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_kite_mcp()

    class FakeSession:
        def __init__(self) -> None:
            self.state = type(
                "S",
                (),
                {"server_info": {"name": "Fake"}, "capabilities": {"tools": {"listChanged": True}}},
            )()

        async def ensure_initialized(self) -> None:
            return None

        async def tools_list(self) -> dict:
            return {"tools": [{"name": "login"}, {"name": "get_profile"}, {"name": "get_holdings"}]}

        async def tools_call(self, *, name: str, arguments: dict) -> dict:  # noqa: ARG002
            if name == "login":
                login_url = (
                    "https://kite.zerodha.com/connect/login?api_key=kitemcp&v=3&redirect_params="
                    + urllib.parse.quote_plus("session_id=abc|123.sig")
                )
                text = f"WARNING: Kite MCP login required.\nLogin: {login_url}"
                return {"content": [{"type": "text", "text": text}], "isError": False}
            if name == "get_profile":
                return {"content": [{"type": "text", "text": "{\"user_id\":\"U1\"}"}], "isError": False}
            if name == "get_holdings":
                return {"content": [{"type": "text", "text": "[{\"tradingsymbol\":\"INFY\"}]"}], "isError": False}
            if name == "get_positions":
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "{\"net\":[{\"tradingsymbol\":\"INFY\",\"product\":\"CNC\",\"quantity\":10,"
                            "\"average_price\":1500}]}",
                        }
                    ],
                    "isError": False,
                }
            if name == "get_orders":
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "[{\"order_id\":\"oid1\",\"tradingsymbol\":\"INFY\",\"transaction_type\":\"BUY\","
                            "\"quantity\":10,\"product\":\"CNC\",\"order_type\":\"MARKET\",\"status\":\"COMPLETE\"}]",
                        }
                    ],
                    "isError": False,
                }
            if name == "get_margins":
                return {"content": [{"type": "text", "text": "{\"equity\":{\"available\":123}}"}], "isError": False}
            return {"content": [{"type": "text", "text": "unknown"}], "isError": True}

    class FakeManager:
        async def get_session(self, *, server_url: str, auth_session_id: str | None):  # noqa: ARG002
            return FakeSession()

    monkeypatch.setattr("app.api.kite_mcp.kite_mcp_sessions", FakeManager())
    monkeypatch.setattr("app.services.kite_mcp.snapshot.kite_mcp_sessions", FakeManager())


def test_status_returns_connected_and_authorized(fake_kite_mcp) -> None:
    resp = client.get("/api/mcp/kite/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True
    assert body["authorized"] is True


def test_auth_start_stores_session_id(fake_kite_mcp) -> None:
    resp = client.get("/api/mcp/kite/auth/start")
    assert resp.status_code == 200
    data = resp.json()
    assert data["login_url"].startswith("https://kite.zerodha.com/connect/login")
    assert "redirect_uri=" in data["login_url"]

    with SessionLocal() as db:
        row = (
            db.query(BrokerSecret)
            .filter(
                BrokerSecret.broker_name == "kite_mcp",
                BrokerSecret.key == "auth_session_id_v1",
                BrokerSecret.user_id.is_(None),
            )
            .one_or_none()
        )
        assert row is not None
        # Encrypted token should not be stored as plaintext.
        assert "abc|123.sig" not in (row.value_encrypted or "")


def test_tools_list(fake_kite_mcp) -> None:
    resp = client.post("/api/mcp/kite/tools/list")
    assert resp.status_code == 200
    tools = resp.json()["tools"]
    assert any(t.get("name") == "get_holdings" for t in tools)


def test_tools_call(fake_kite_mcp) -> None:
    resp = client.post("/api/mcp/kite/tools/call", json={"name": "get_profile", "arguments": {}})
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result.get("isError") is False


def test_snapshot_fetch(fake_kite_mcp) -> None:
    resp = client.post("/api/mcp/kite/snapshot/fetch?account_id=default")
    assert resp.status_code == 200
    snap = resp.json()
    assert snap["source"] == "kite_mcp"
    assert len(snap["holdings"]) == 1
    assert len(snap["positions"]) == 1
    assert len(snap["orders"]) == 1


def test_auth_callback_stores_session_id(fake_kite_mcp) -> None:
    resp = client.get(
        "/api/mcp/kite/auth/callback?session_id=cb|token.sig&request_token=req123",
        follow_redirects=False,
    )
    assert resp.status_code in {302, 303, 307, 308}

    with SessionLocal() as db:
        row = (
            db.query(BrokerSecret)
            .filter(
                BrokerSecret.broker_name == "kite_mcp",
                BrokerSecret.key == "auth_session_id_v1",
                BrokerSecret.user_id.is_(None),
            )
            .one_or_none()
        )
        assert row is not None
        assert "cb|token.sig" not in (row.value_encrypted or "")

        rt = (
            db.query(BrokerSecret)
            .filter(
                BrokerSecret.broker_name == "kite_mcp",
                BrokerSecret.key == "request_token_v1",
                BrokerSecret.user_id.is_(None),
            )
            .one_or_none()
        )
        assert rt is not None
        assert "req123" not in (rt.value_encrypted or "")
