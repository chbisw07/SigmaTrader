from __future__ import annotations

import json
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
    os.environ["ST_AI_EXECUTION_KILL_SWITCH"] = "0"
    os.environ["ST_CRYPTO_KEY"] = "test-remote-tool-arg-repair"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _enable_ai_provider() -> None:
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


@pytest.fixture()
def fake_kite_mcp_remote_quotes_schema(monkeypatch: pytest.MonkeyPatch):
    # Enable Kite MCP + hybrid gateway toggles (remote-only reasoner).
    # Use a unique server_url to avoid cross-test contamination from the global tools cache.
    server_url = "https://mcp.kite.trade/sse?test=remote_tool_arg_repair"
    resp = client.put(
        "/api/settings/ai",
        json={
            "feature_flags": {"kite_mcp_enabled": True},
            "kite_mcp": {"server_url": server_url},
            "hybrid_llm": {
                "enabled": True,
                "mode": "REMOTE_ONLY",
                "allow_remote_market_data_tools": True,
                "allow_remote_account_digests": False,
                "remote_portfolio_detail_level": "OFF",
            },
        },
    )
    assert resp.status_code == 200

    calls: dict[str, int] = {}

    class FakeSession:
        def __init__(self) -> None:
            self.state = type("S", (), {"server_info": {"name": "Fake"}, "capabilities": {"tools": {}}})()

        async def ensure_initialized(self) -> None:
            return None

        async def tools_list(self):
            return {
                "tools": [
                    {
                        "name": "get_quotes",
                        "description": "Return quotes for instruments",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"instruments": {"type": "array", "items": {"type": "string"}}},
                            "required": ["instruments"],
                            "additionalProperties": False,
                        },
                        "annotations": {"readOnlyHint": True, "destructiveHint": False},
                    },
                ]
            }

        async def tools_call(self, *, name: str, arguments: dict):  # noqa: ARG002
            calls[name] = calls.get(name, 0) + 1
            if name == "get_quotes":
                # Ensure arg normalization happened.
                assert isinstance(arguments, dict)
                assert arguments.get("instruments") == ["NSE:INFY"]
                return {"content": [{"type": "text", "text": "{\"NSE:INFY\":{\"last_price\":1370.5}}"}], "isError": False}
            return {"content": [{"type": "text", "text": "nope"}], "isError": True}

    class FakeManager:
        async def get_session(self, *, server_url: str, auth_session_id: str | None):  # noqa: ARG002
            return FakeSession()

    mgr = FakeManager()
    # Clear any cached tool lists for this URL (defensive).
    from app.services.ai_toolcalling import tools_cache as _tools_cache

    _tools_cache._CACHE.pop(server_url.strip().lower(), None)
    monkeypatch.setattr("app.services.ai_toolcalling.orchestrator.kite_mcp_sessions", mgr)
    monkeypatch.setattr("app.services.ai_toolcalling.orchestrator.get_auth_session_id", lambda *a, **k: None)
    monkeypatch.setattr("app.api.kite_mcp.kite_mcp_sessions", mgr)
    monkeypatch.setattr("app.api.kite_mcp.get_auth_session_id", lambda *a, **k: None)
    monkeypatch.setattr("app.services.kite_mcp.snapshot.kite_mcp_sessions", mgr)
    monkeypatch.setattr("app.services.kite_mcp.snapshot.get_auth_session_id", lambda *a, **k: None)

    return calls


def test_remote_lsg_normalizes_symbols_to_instruments(monkeypatch: pytest.MonkeyPatch, fake_kite_mcp_remote_quotes_schema) -> None:
    _enable_ai_provider()

    from app.services.ai_toolcalling import orchestrator as orch
    from app.services.ai_toolcalling.openai_toolcaller import OpenAiAssistantTurn, OpenAiToolCall

    calls = {"n": 0}

    async def fake_openai_chat_with_tools(*, api_key, model, messages, tools, **kwargs):  # noqa: ANN001, ARG001
        calls["n"] += 1
        if calls["n"] == 1:
            # Intentionally use the common LLM key "symbols" instead of schema-key "instruments".
            return OpenAiAssistantTurn(
                content="",
                tool_calls=[
                    OpenAiToolCall(
                        tool_call_id="r1",
                        name="get_quotes",
                        arguments={"symbols": ["INFY"], "exchange": "NSE"},
                    )
                ],
                raw={},
            )
        return OpenAiAssistantTurn(content="OK", tool_calls=[], raw={})

    monkeypatch.setattr(orch, "openai_chat_with_tools", fake_openai_chat_with_tools)

    resp = client.post("/api/ai/chat", json={"account_id": "default", "message": "What is INFY quote?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["assistant_message"] == "OK"
    assert any(t["name"] == "get_quotes" and t["status"] == "ok" for t in body["tool_calls"])


def test_remote_fallback_includes_last_tool_error(monkeypatch: pytest.MonkeyPatch, fake_kite_mcp_remote_quotes_schema) -> None:
    _enable_ai_provider()

    from app.services.ai_toolcalling import orchestrator as orch
    from app.services.ai_toolcalling.openai_toolcaller import OpenAiAssistantTurn, OpenAiToolCall

    calls = {"n": 0}

    async def fake_openai_chat_with_tools(*, api_key, model, messages, tools, **kwargs):  # noqa: ANN001, ARG001
        calls["n"] += 1
        if calls["n"] == 1:
            # Missing required args -> LSG invalid_args.
            return OpenAiAssistantTurn(
                content="",
                tool_calls=[OpenAiToolCall(tool_call_id="r1", name="get_quotes", arguments={})],
                raw={},
            )
        # Keep returning empty JSON so the orchestrator eventually hits the fallback.
        return OpenAiAssistantTurn(content="", tool_calls=[], raw={})

    monkeypatch.setattr(orch, "openai_chat_with_tools", fake_openai_chat_with_tools)

    resp = client.post("/api/ai/chat", json={"account_id": "default", "message": "What is INFY quote?"})
    assert resp.status_code == 200
    body = resp.json()
    assert "get_quotes" in body["assistant_message"]
    assert "Missing required arg" in body["assistant_message"]
    assert body["assistant_message"] != "I couldn't complete that request right now."
