from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.schemas.mcp_servers import McpSettings, McpTransport
from app.services.ai_trading_manager.thread_state import patch_thread_state


client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_AI_ASSISTANT_ENABLED"] = "1"
    os.environ["ST_AI_EXECUTION_KILL_SWITCH"] = "0"
    os.environ["ST_CRYPTO_KEY"] = "test-ai-approvals"
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
def fake_kite_and_tavily(monkeypatch: pytest.MonkeyPatch):
    # Hybrid gateway enabled (remote reasoner).
    resp = client.put(
        "/api/settings/ai",
        json={
            "feature_flags": {"kite_mcp_enabled": True},
            "kite_mcp": {"server_url": "https://mcp.kite.trade/sse"},
            "hybrid_llm": {
                "enabled": True,
                "mode": "REMOTE_ONLY",
                "allow_remote_market_data_tools": True,
                "allow_remote_account_digests": True,
                "remote_portfolio_detail_level": "DIGEST_ONLY",
            },
            "tool_guardrails": {"tavily_max_calls_per_session": 10, "tavily_warning_threshold": 8},
        },
    )
    assert resp.status_code == 200

    class FakeKiteSession:
        def __init__(self) -> None:
            self.state = type("S", (), {"server_info": {"name": "Fake"}, "capabilities": {"tools": {}}})()

        async def ensure_initialized(self) -> None:
            return None

        async def tools_list(self):
            return {
                "tools": [
                    {
                        "name": "get_holdings",
                        "description": "Holdings",
                        "inputSchema": {"type": "object", "properties": {}, "required": []},
                        "annotations": {"readOnlyHint": True, "destructiveHint": False},
                    }
                ]
            }

        async def tools_call(self, *, name: str, arguments: dict):  # noqa: ARG002
            if name == "get_holdings":
                return {"content": [{"type": "text", "text": "[{\"tradingsymbol\":\"INFY\",\"quantity\":1}]"}], "isError": False}
            return {"content": [{"type": "text", "text": "nope"}], "isError": True}

    class FakeKiteManager:
        async def get_session(self, *, server_url: str, auth_session_id: str | None):  # noqa: ARG002
            return FakeKiteSession()

    mgr = FakeKiteManager()
    monkeypatch.setattr("app.services.ai_toolcalling.orchestrator.kite_mcp_sessions", mgr)
    monkeypatch.setattr("app.services.ai_toolcalling.orchestrator.get_auth_session_id", lambda *a, **k: None)
    monkeypatch.setattr("app.api.kite_mcp.kite_mcp_sessions", mgr)
    monkeypatch.setattr("app.api.kite_mcp.get_auth_session_id", lambda *a, **k: None)
    monkeypatch.setattr("app.services.kite_mcp.snapshot.kite_mcp_sessions", mgr)
    monkeypatch.setattr("app.services.kite_mcp.snapshot.get_auth_session_id", lambda *a, **k: None)

    class FakeTavilySession:
        def __init__(self) -> None:
            self.state = type("S", (), {"server_info": {"name": "FakeTavily"}, "capabilities": {"tools": {}}})()

        async def ensure_initialized(self) -> None:
            return None

        async def tools_list(self):
            return {
                "tools": [
                    {
                        "name": "tavily_search",
                        "description": "Search the web",
                        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
                        "annotations": {"readOnlyHint": True, "destructiveHint": False},
                    }
                ]
            }

        async def tools_call(self, *, name: str, arguments: dict):  # noqa: ARG002
            if name == "tavily_search":
                q = str(arguments.get("query") or "")
                return {"content": [{"type": "text", "text": json.dumps({"query": q, "results": [{"title": "t1"}]})}], "isError": False}
            return {"content": [{"type": "text", "text": "nope"}], "isError": True}

    class FakeExternalMgr:
        async def get_client(self, *, server_url: str):  # noqa: ARG002
            return FakeTavilySession()

    monkeypatch.setattr("app.services.ai_toolcalling.orchestrator.external_mcp_sessions", FakeExternalMgr())

    # Pretend Tavily MCP is enabled.
    tavily_settings = McpSettings(
        servers={
            "tavily": {
                "label": "Tavily",
                "enabled": True,
                "transport": McpTransport.sse,
                "url": "https://mcp.tavily.com/mcp",
                "ai_enabled": True,
            }
        }
    )
    monkeypatch.setattr(
        "app.services.ai_toolcalling.orchestrator.get_mcp_settings_with_source",
        lambda *a, **k: (tavily_settings, "db"),
    )


def test_remote_portfolio_detail_requires_approval(monkeypatch: pytest.MonkeyPatch, fake_kite_and_tavily) -> None:
    _enable_ai_provider()

    from app.services.ai_toolcalling import orchestrator as orch
    from app.services.ai_toolcalling.openai_toolcaller import OpenAiAssistantTurn

    async def fake_openai_chat_plain(*, api_key, model, messages, **kwargs):  # noqa: ANN001, ARG001
        # If tool_result is present, respond with a final message.
        if any(isinstance(m, dict) and isinstance(m.get("content"), str) and "\"tool_result\"" in m.get("content") for m in (messages or [])):
            return OpenAiAssistantTurn(content=json.dumps({"final_message": "OK"}), tool_calls=[], raw={})
        return OpenAiAssistantTurn(
            content=json.dumps(
                {
                    "tool_requests": [
                        {
                            "request_id": "r1",
                            "tool_name": "get_holdings",
                            "args": {},
                            "reason": "need holdings",
                            "risk_tier": "LOW",
                        }
                    ]
                }
            ),
            tool_calls=[],
            raw={},
        )

    monkeypatch.setattr(orch, "openai_chat_plain", fake_openai_chat_plain)

    resp = client.post("/api/ai/chat", json={"account_id": "default", "thread_id": "t1", "message": "show holdings"})
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("assistant_message") == ""
    appr = body.get("approval_required")
    assert isinstance(appr, dict)
    assert appr.get("kind") == "remote_portfolio_detail"
    assert appr.get("authorization_message_id")

    # Approve once, then resume.
    ok = client.post(
        "/api/ai/approvals",
        json={"account_id": "default", "thread_id": "t1", "kind": "remote_portfolio_detail", "decision": "allow_once"},
    )
    assert ok.status_code == 200

    r2 = client.post(
        "/api/ai/chat/resume",
        json={"account_id": "default", "thread_id": "t1", "authorization_message_id": appr["authorization_message_id"]},
    )
    assert r2.status_code == 200
    assert r2.json().get("assistant_message") == "OK"


def test_tavily_over_limit_requires_approval_and_cache(monkeypatch: pytest.MonkeyPatch, fake_kite_and_tavily) -> None:
    _enable_ai_provider()

    # Seed thread state to be at the limit already.
    with SessionLocal() as db:
        patch_thread_state(
            db,
            account_id="default",
            thread_id="t2",
            user_id=None,
            patch={"tavily_calls_session": 10, "tavily_extra_calls_allowed": 0},
        )

    from app.services.ai_toolcalling import orchestrator as orch
    from app.services.ai_toolcalling.openai_toolcaller import OpenAiAssistantTurn

    async def fake_openai_chat_plain(*, api_key, model, messages, **kwargs):  # noqa: ANN001, ARG001
        if any(isinstance(m, dict) and isinstance(m.get("content"), str) and "\"tool_result\"" in m.get("content") for m in (messages or [])):
            return OpenAiAssistantTurn(content=json.dumps({"final_message": "OK"}), tool_calls=[], raw={})
        return OpenAiAssistantTurn(
            content=json.dumps(
                {
                    "tool_requests": [
                        {
                            "request_id": "r1",
                            "tool_name": "tavily_search",
                            "args": {"query": "what is INFY"},
                            "reason": "need web context",
                            "risk_tier": "LOW",
                        }
                    ]
                }
            ),
            tool_calls=[],
            raw={},
        )

    monkeypatch.setattr(orch, "openai_chat_plain", fake_openai_chat_plain)

    r1 = client.post("/api/ai/chat", json={"account_id": "default", "thread_id": "t2", "message": "search INFY"})
    assert r1.status_code == 200
    appr = r1.json().get("approval_required")
    assert isinstance(appr, dict)
    assert appr.get("kind") == "tavily_over_limit"

    ok = client.post(
        "/api/ai/approvals",
        json={"account_id": "default", "thread_id": "t2", "kind": "tavily_over_limit", "decision": "allow_once", "grant": 1},
    )
    assert ok.status_code == 200

    r2 = client.post(
        "/api/ai/chat/resume",
        json={"account_id": "default", "thread_id": "t2", "authorization_message_id": appr["authorization_message_id"]},
    )
    assert r2.status_code == 200
    assert r2.json().get("assistant_message") == "OK"

    # Second resume with identical query should hit cache and not require another over-limit approval.
    r3 = client.post(
        "/api/ai/chat/resume",
        json={"account_id": "default", "thread_id": "t2", "authorization_message_id": appr["authorization_message_id"]},
    )
    assert r3.status_code == 200
    assert r3.json().get("assistant_message") == "OK"

