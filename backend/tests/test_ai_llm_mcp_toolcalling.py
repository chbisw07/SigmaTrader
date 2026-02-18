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
    os.environ["ST_AI_ASSISTANT_ENABLED"] = "1"
    os.environ["ST_CRYPTO_KEY"] = "test-ai-toolcalling-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _enable_ai_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    # Enable provider + create key + set config.
    k = client.post(
        "/api/ai/keys",
        json={"provider": "openai", "key_name": "k1", "api_key_value": "sk-test-1234567890"},
    ).json()
    resp_cfg = client.put(
        "/api/ai/config",
        json={
            "enabled": True,
            "provider": "openai",
            "active_key_id": k["id"],
            "model": "gpt-test",
            "do_not_send_pii": True,
        },
    )
    assert resp_cfg.status_code == 200

    # Fake OpenAI tool-calling responses.
    from app.services.ai_toolcalling import orchestrator as orch
    from app.services.ai_toolcalling.openai_toolcaller import OpenAiAssistantTurn, OpenAiToolCall

    calls = {"n": 0}

    async def fake_openai_chat_with_tools(*, api_key, model, messages, tools, **kwargs):  # noqa: ANN001
        calls["n"] += 1
        if calls["n"] == 1:
            return OpenAiAssistantTurn(
                content="",
                tool_calls=[OpenAiToolCall(tool_call_id="tc1", name="get_holdings", arguments={})],
                raw={},
            )
        return OpenAiAssistantTurn(
            content="Top 5 holdings: INFY, TCS, RELIANCE, HDFCBANK, ICICIBANK",
            tool_calls=[],
            raw={},
        )

    monkeypatch.setattr(orch, "openai_chat_with_tools", fake_openai_chat_with_tools)


@pytest.fixture()
def fake_kite_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    # Enable Kite MCP in settings.
    resp = client.put(
        "/api/settings/ai",
        json={"feature_flags": {"kite_mcp_enabled": True}, "kite_mcp": {"server_url": "https://mcp.kite.trade/sse"}},
    )
    assert resp.status_code == 200

    class FakeSession:
        def __init__(self) -> None:
            self.state = type("S", (), {"server_info": {"name": "Fake"}, "capabilities": {"tools": {}}})()

        async def ensure_initialized(self) -> None:
            return None

        async def tools_list(self):
            return {
                "tools": [
                    {
                        "name": "get_holdings",
                        "description": "Return holdings",
                        "inputSchema": {"type": "object", "properties": {}},
                        "annotations": {"readOnlyHint": True, "destructiveHint": False},
                    },
                    {
                        "name": "cancel_order",
                        "description": "Cancel order",
                        "inputSchema": {"type": "object", "properties": {"order_id": {"type": "string"}}},
                        "annotations": {"readOnlyHint": False, "destructiveHint": True},
                    },
                ]
            }

        async def tools_call(self, *, name: str, arguments: dict):  # noqa: ARG002
            if name == "get_holdings":
                return {"content": [{"type": "text", "text": "[{\"tradingsymbol\":\"INFY\"}]"}], "isError": False}
            return {"content": [{"type": "text", "text": "nope"}], "isError": True}

    class FakeManager:
        async def get_session(self, *, server_url: str, auth_session_id: str | None):  # noqa: ARG002
            return FakeSession()

    monkeypatch.setattr("app.services.ai_toolcalling.orchestrator.kite_mcp_sessions", FakeManager())
    monkeypatch.setattr("app.services.ai_toolcalling.orchestrator.get_auth_session_id", lambda *a, **k: None)


def test_chat_fetch_holdings(monkeypatch: pytest.MonkeyPatch, fake_kite_mcp) -> None:
    _enable_ai_provider(monkeypatch)

    resp = client.post("/api/ai/chat", json={"account_id": "default", "message": "fetch my top 5 holdings"})
    assert resp.status_code == 200
    body = resp.json()
    assert "Top 5 holdings" in body["assistant_message"]
    assert body["decision_id"]
    assert body["tool_calls"] and body["tool_calls"][0]["name"] == "get_holdings"

    tr = client.get(f"/api/ai/decision-traces/{body['decision_id']}")
    assert tr.status_code == 200
    assert tr.json()["user_message"] == "fetch my top 5 holdings"


def test_chat_blocks_trade_tool(monkeypatch: pytest.MonkeyPatch, fake_kite_mcp) -> None:
    _enable_ai_provider(monkeypatch)

    from app.services.ai_toolcalling import orchestrator as orch
    from app.services.ai_toolcalling.openai_toolcaller import OpenAiAssistantTurn, OpenAiToolCall

    calls = {"n": 0}

    async def fake_openai_chat_with_tools(*, api_key, model, messages, tools, **kwargs):  # noqa: ANN001
        calls["n"] += 1
        if calls["n"] == 1:
            return OpenAiAssistantTurn(
                content="",
                tool_calls=[OpenAiToolCall(tool_call_id="tc2", name="cancel_order", arguments={"order_id": "oid1"})],
                raw={},
            )
        return OpenAiAssistantTurn(
            content="I can't cancel orders from SigmaTrader right now (policy veto).",
            tool_calls=[],
            raw={},
        )

    monkeypatch.setattr(orch, "openai_chat_with_tools", fake_openai_chat_with_tools)

    resp = client.post("/api/ai/chat", json={"account_id": "default", "message": "cancel my last order"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["tool_calls"] and body["tool_calls"][0]["status"] == "blocked"
