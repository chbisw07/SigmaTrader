from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.main import app

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_AI_ASSISTANT_ENABLED"] = "0"
    os.environ["ST_AI_EXECUTION_ENABLED"] = "0"
    os.environ["ST_KITE_MCP_ENABLED"] = "0"
    os.environ["ST_MONITORING_ENABLED"] = "0"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_get_ai_settings_returns_defaults() -> None:
    resp = client.get("/api/settings/ai")
    assert resp.status_code == 200
    data = resp.json()
    assert data["feature_flags"]["ai_assistant_enabled"] is False
    assert data["feature_flags"]["ai_execution_enabled"] is False
    assert data["feature_flags"]["kite_mcp_enabled"] is False
    assert data["feature_flags"]["monitoring_enabled"] is False
    assert data["kill_switch"]["ai_execution_kill_switch"] is False
    assert data["kite_mcp"]["last_status"] in {"unknown", "disconnected", "error", "connected"}
    assert data["llm_provider"]["provider"] in {"stub", "openai", "anthropic", "local"}


def test_put_ai_settings_persists_and_audits() -> None:
    payload = {
        "feature_flags": {"ai_assistant_enabled": True, "kite_mcp_enabled": True},
        "kite_mcp": {
            "server_url": "http://localhost:9999",
            "transport_mode": "remote",
            "auth_method": "none",
            "auth_profile_ref": "profile-1",
            "scopes": {"read_only": True, "trade": False},
            "broker_adapter": "zerodha",
        },
        "llm_provider": {
            "enabled": False,
            "provider": "stub",
            "do_not_send_pii": True,
            "limits": {},
        },
    }
    resp = client.put("/api/settings/ai", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["feature_flags"]["ai_assistant_enabled"] is True
    assert data["feature_flags"]["kite_mcp_enabled"] is True
    assert data["kite_mcp"]["server_url"] == "http://localhost:9999"
    assert data["kite_mcp"]["auth_profile_ref"] == "profile-1"

    # Reload via GET to ensure persistence.
    resp2 = client.get("/api/settings/ai")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["kite_mcp"]["server_url"] == "http://localhost:9999"

    audit = client.get("/api/settings/ai/audit?category=AI_SETTINGS&limit=50").json()
    assert audit["items"]
    assert any(i["category"] == "AI_SETTINGS" for i in audit["items"])


def test_execution_enable_blocked_without_connected_mcp() -> None:
    # Even if MCP is enabled and URL is set, execution should be blocked until
    # the connection test marks it connected.
    resp = client.put(
        "/api/settings/ai",
        json={
            "feature_flags": {"kite_mcp_enabled": True, "ai_execution_enabled": True},
            "kite_mcp": {"server_url": "http://localhost:9999"},
        },
    )
    assert resp.status_code == 400
    assert "connected" in (resp.text or "").lower()


def test_kite_test_updates_status_and_allows_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import ai_settings as ai_settings_api
    from app.clients.kite_mcp import KiteMcpTestResult

    class FakeKiteClient:
        def __init__(self, *, timeout_seconds: int = 5) -> None:
            self.timeout_seconds = timeout_seconds

        def test_connection(self, *, server_url: str, fetch_capabilities: bool = True) -> KiteMcpTestResult:
            return KiteMcpTestResult(
                ok=True,
                status_code=200,
                used_endpoint=f"{server_url.rstrip('/')}/health",
                health={"ok": True},
                capabilities={"tools": ["kite.place_order", "kite.positions"]} if fetch_capabilities else None,
            )

    monkeypatch.setattr(ai_settings_api, "HttpKiteMCPClient", FakeKiteClient)

    # Enable Kite MCP feature flag (required for execution enable).
    resp0 = client.put("/api/settings/ai", json={"feature_flags": {"kite_mcp_enabled": True}})
    assert resp0.status_code == 200

    # Test connection (also persists server_url when provided in payload).
    resp = client.post(
        "/api/settings/ai/kite/test",
        json={"server_url": "http://localhost:5555", "fetch_capabilities": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "connected"
    assert "capabilities" in body

    # Now enabling execution should succeed.
    resp2 = client.put("/api/settings/ai", json={"feature_flags": {"ai_execution_enabled": True}})
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["feature_flags"]["ai_execution_enabled"] is True

    audit = client.get("/api/settings/ai/audit?category=KITE_MCP&limit=50").json()
    assert audit["items"]
    assert any(i["category"] == "KITE_MCP" for i in audit["items"])
