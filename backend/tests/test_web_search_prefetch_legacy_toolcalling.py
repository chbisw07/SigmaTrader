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
    os.environ["ST_CRYPTO_KEY"] = "test-ws-prefetch-legacy"
    os.environ["ST_ENABLE_REMOTE_WEB_SEARCH"] = "1"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _enable_ai_provider(*, enable_web_search: bool) -> None:
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
            "enable_web_search": bool(enable_web_search),
        },
    )
    assert resp_cfg.status_code == 200


def test_web_search_prefetch_inserts_context_when_hybrid_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_ai_provider(enable_web_search=True)

    # Enable Kite MCP (required by /api/ai/chat even if we don't end up calling tools).
    resp = client.put(
        "/api/settings/ai",
        json={"feature_flags": {"kite_mcp_enabled": True}, "kite_mcp": {"server_url": "https://mcp.kite.trade/sse"}},
    )
    assert resp.status_code == 200

    # Explicitly disable hybrid gateway.
    resp = client.put("/api/settings/ai", json={"hybrid_llm": {"enabled": False}})
    assert resp.status_code == 200

    from app.services.ai_toolcalling import orchestrator as orch
    from app.services.ai_toolcalling.openai_toolcaller import OpenAiAssistantTurn

    class FakeSession:
        def __init__(self) -> None:
            self.state = type("S", (), {"server_info": {"name": "Fake"}, "capabilities": {"tools": {}}})()

        async def ensure_initialized(self) -> None:
            return None

        async def tools_list(self):
            return {
                "tools": [
                    {
                        "name": "get_ltp",
                        "description": "Return LTP",
                        "inputSchema": {"type": "object", "properties": {"symbols": {"type": "array", "items": {"type": "string"}}}, "required": ["symbols"], "additionalProperties": False},
                        "annotations": {"readOnlyHint": True, "destructiveHint": False},
                    },
                ]
            }

        async def tools_call(self, *, name: str, arguments: dict):  # noqa: ARG002
            return {"content": [{"type": "text", "text": "{}"}], "isError": False}

    class FakeManager:
        async def get_session(self, *, server_url: str, auth_session_id: str | None):  # noqa: ARG002
            return FakeSession()

    mgr = FakeManager()
    monkeypatch.setattr("app.services.ai_toolcalling.orchestrator.kite_mcp_sessions", mgr)
    monkeypatch.setattr("app.services.ai_toolcalling.orchestrator.get_auth_session_id", lambda *a, **k: None)

    async def fake_responses_plain(**kwargs):  # noqa: ANN001
        # Return a short web brief and a meta domain list (no URLs).
        return OpenAiAssistantTurn(
            content="News: X happened (2026-03-06, example.com).",
            tool_calls=[],
            raw={"web_search": {"calls": 1, "source_domains": ["example.com"]}},
        )

    seen_messages: list[list[dict]] = []

    async def fake_openai_chat_with_tools(*, messages, **kwargs):  # noqa: ANN001
        seen_messages.append(list(messages or []))
        return OpenAiAssistantTurn(content="OK", tool_calls=[], raw={})

    monkeypatch.setattr(orch, "openai_responses_plain", fake_responses_plain)
    monkeypatch.setattr(orch, "openai_chat_with_tools", fake_openai_chat_with_tools)

    resp2 = client.post("/api/ai/chat", json={"account_id": "default", "message": "Use web search: what happened today?"})
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["assistant_message"] == "OK"
    assert seen_messages, "expected legacy toolcalling to run"
    # Ensure web_search_context system message is injected.
    joined = "\n".join(str(m.get("content") or "") for m in seen_messages[-1] if m.get("role") == "system")
    assert "web_search_context" in joined


def test_no_prefetch_when_message_not_web_like(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_ai_provider(enable_web_search=True)
    resp = client.put(
        "/api/settings/ai",
        json={"feature_flags": {"kite_mcp_enabled": True}, "kite_mcp": {"server_url": "https://mcp.kite.trade/sse"}},
    )
    assert resp.status_code == 200
    resp = client.put("/api/settings/ai", json={"hybrid_llm": {"enabled": False}})
    assert resp.status_code == 200

    from app.services.ai_toolcalling import orchestrator as orch
    from app.services.ai_toolcalling.openai_toolcaller import OpenAiAssistantTurn

    class FakeSession:
        def __init__(self) -> None:
            self.state = type("S", (), {"server_info": {"name": "Fake"}, "capabilities": {"tools": {}}})()

        async def ensure_initialized(self) -> None:
            return None

        async def tools_list(self):
            return {
                "tools": [
                    {
                        "name": "get_ltp",
                        "description": "Return LTP",
                        "inputSchema": {"type": "object", "properties": {"symbols": {"type": "array", "items": {"type": "string"}}}, "required": ["symbols"], "additionalProperties": False},
                        "annotations": {"readOnlyHint": True, "destructiveHint": False},
                    },
                ]
            }

        async def tools_call(self, *, name: str, arguments: dict):  # noqa: ARG002
            return {"content": [{"type": "text", "text": "{}"}], "isError": False}

    class FakeManager:
        async def get_session(self, *, server_url: str, auth_session_id: str | None):  # noqa: ARG002
            return FakeSession()

    mgr = FakeManager()
    monkeypatch.setattr("app.services.ai_toolcalling.orchestrator.kite_mcp_sessions", mgr)
    monkeypatch.setattr("app.services.ai_toolcalling.orchestrator.get_auth_session_id", lambda *a, **k: None)

    called = {"ws": 0}

    async def fake_responses_plain(**kwargs):  # noqa: ANN001
        called["ws"] += 1
        return OpenAiAssistantTurn(content="x", tool_calls=[], raw={})

    async def fake_openai_chat_with_tools(**kwargs):  # noqa: ANN001
        return OpenAiAssistantTurn(content="OK", tool_calls=[], raw={})

    monkeypatch.setattr(orch, "openai_responses_plain", fake_responses_plain)
    monkeypatch.setattr(orch, "openai_chat_with_tools", fake_openai_chat_with_tools)

    resp2 = client.post("/api/ai/chat", json={"account_id": "default", "message": "What is ATR?"})
    assert resp2.status_code == 200
    assert resp2.json()["assistant_message"] == "OK"
    assert called["ws"] == 0
