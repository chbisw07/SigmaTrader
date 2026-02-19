from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from app.ai.safety.payload_inspector import inspect_llm_payload
from app.ai.safety.safe_summary_registry import summarize_tool_for_llm
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.main import app

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_AI_ASSISTANT_ENABLED"] = "1"
    os.environ["ST_CRYPTO_KEY"] = "test-ai-pii-safety-secret"
    os.environ["ST_HASH_SALT"] = "test-hash-salt"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _enable_openai_provider(*, do_not_send_pii: bool) -> None:
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
            "do_not_send_pii": do_not_send_pii,
        },
    )
    assert resp_cfg.status_code == 200


@pytest.fixture()
def fake_kite_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
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
                        "name": "get_positions",
                        "description": "Return positions",
                        "inputSchema": {"type": "object", "properties": {}},
                        "annotations": {"readOnlyHint": True, "destructiveHint": False},
                    },
                    {
                        "name": "get_orders",
                        "description": "Return orders",
                        "inputSchema": {"type": "object", "properties": {}},
                        "annotations": {"readOnlyHint": True, "destructiveHint": False},
                    },
                    {
                        "name": "get_margins",
                        "description": "Return margins",
                        "inputSchema": {"type": "object", "properties": {}},
                        "annotations": {"readOnlyHint": True, "destructiveHint": False},
                    },
                    {
                        "name": "get_profile",
                        "description": "Return profile (contains ids)",
                        "inputSchema": {"type": "object", "properties": {}},
                        "annotations": {"readOnlyHint": True, "destructiveHint": False},
                    },
                ]
            }

        async def tools_call(self, *, name: str, arguments: dict):  # noqa: ARG002
            if name == "get_holdings":
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                [
                                    {
                                        "tradingsymbol": "INFY",
                                        "quantity": 14,
                                        "average_price": 1384.2,
                                        "last_price": 1370.5,
                                        "pnl": -191.8,
                                        "instrument_token": 123,  # forbidden in operator view (must not leak)
                                    }
                                ]
                            ),
                        }
                    ],
                    "isError": False,
                }
            if name == "get_profile":
                return {"content": [{"type": "text", "text": "{\"user_id\":\"CZC754\"}"}], "isError": False}
            if name == "get_positions":
                return {"content": [{"type": "text", "text": "{\"net\": []}"}], "isError": False}
            if name == "get_orders":
                return {"content": [{"type": "text", "text": "[]"}], "isError": False}
            if name == "get_margins":
                return {"content": [{"type": "text", "text": "{\"equity\": 100000}"}], "isError": False}
            return {"content": [{"type": "text", "text": "nope"}], "isError": True}

    class FakeManager:
        async def get_session(self, *, server_url: str, auth_session_id: str | None):  # noqa: ARG002
            return FakeSession()

    mgr = FakeManager()
    monkeypatch.setattr("app.services.ai_toolcalling.orchestrator.kite_mcp_sessions", mgr)
    monkeypatch.setattr("app.services.ai_toolcalling.orchestrator.get_auth_session_id", lambda *a, **k: None)
    monkeypatch.setattr("app.api.kite_mcp.kite_mcp_sessions", mgr)
    monkeypatch.setattr("app.api.kite_mcp.get_auth_session_id", lambda *a, **k: None)
    monkeypatch.setattr("app.services.kite_mcp.snapshot.kite_mcp_sessions", mgr)
    monkeypatch.setattr("app.services.kite_mcp.snapshot.get_auth_session_id", lambda *a, **k: None)


def test_safe_summaries_are_inspector_clean() -> None:
    settings = get_settings()
    holdings_op = {
        "status": "success",
        "data": [
            {
                "tradingsymbol": "INFY",
                "quantity": 14,
                "average_price": 1384.2,
                "last_price": 1370.5,
                "pnl": -191.8,
                "instrument_token": 123,
                "user_id": "CZC754",
            }
        ],
    }
    summary = summarize_tool_for_llm(settings, tool_name="get_holdings", operator_payload=holdings_op)
    # Must not contain forbidden keys/patterns.
    inspect_llm_payload(summary, fail_closed=True)

    orders_op = [
        {
            "order_id": "oid-123",
            "exchange_order_id": "ex-999",
            "tradingsymbol": "INFY",
            "quantity": 1,
            "status": "COMPLETE",
        }
    ]
    summary2 = summarize_tool_for_llm(settings, tool_name="get_orders", operator_payload=orders_op)
    inspect_llm_payload(summary2, fail_closed=True)
    assert "id_hash" in json.dumps(summary2)
    assert "order_id" not in json.dumps(summary2)


def test_orchestrator_never_sends_operator_payload_to_remote_llm(
    monkeypatch: pytest.MonkeyPatch, fake_kite_mcp
) -> None:
    _enable_openai_provider(do_not_send_pii=True)

    from app.services.ai_toolcalling.openai_toolcaller import OpenAiAssistantTurn, OpenAiToolCall
    from app.services.ai_toolcalling import orchestrator as orch

    calls: list[dict] = []

    async def fake_openai_chat_with_tools(*, api_key, model, messages, tools, **kwargs):  # noqa: ANN001
        _ = api_key, model, tools, kwargs
        # Record the outbound messages so the test can inspect them.
        calls.append({"messages": messages})
        payload_text = json.dumps(messages, ensure_ascii=False)
        # Operator-only keys must never appear in outbound payloads.
        assert "instrument_token" not in payload_text
        assert "tradingsymbol" not in payload_text
        assert "user_id" not in payload_text
        if len(calls) == 1:
            return OpenAiAssistantTurn(
                content="",
                tool_calls=[OpenAiToolCall(tool_call_id="tc1", name="get_holdings", arguments={})],
                raw={},
            )
        return OpenAiAssistantTurn(content="OK", tool_calls=[], raw={})

    monkeypatch.setattr(orch, "openai_chat_with_tools", fake_openai_chat_with_tools)

    # Use a prompt that does NOT trigger the deterministic "show/list/fetch" direct path.
    resp = client.post("/api/ai/chat", json={"account_id": "default", "message": "what are my top holdings?"})
    assert resp.status_code == 200
    assert len(calls) >= 2  # tool call + final response


def test_missing_safe_summary_blocks_remote_continuation(
    monkeypatch: pytest.MonkeyPatch, fake_kite_mcp
) -> None:
    _enable_openai_provider(do_not_send_pii=True)

    from app.services.ai_toolcalling.openai_toolcaller import OpenAiAssistantTurn, OpenAiToolCall
    from app.services.ai_toolcalling import orchestrator as orch

    calls = {"n": 0}

    async def fake_openai_chat_with_tools(*, api_key, model, messages, tools, **kwargs):  # noqa: ANN001
        _ = api_key, model, messages, tools, kwargs
        calls["n"] += 1
        if calls["n"] == 1:
            return OpenAiAssistantTurn(
                content="",
                tool_calls=[OpenAiToolCall(tool_call_id="tcX", name="get_profile", arguments={})],
                raw={},
            )
        return OpenAiAssistantTurn(
            content=(
                "I can't access that tool from SigmaTrader right now. "
                "I can read holdings/positions/margins/orders."
            ),
            tool_calls=[],
            raw={},
        )

    monkeypatch.setattr(orch, "openai_chat_with_tools", fake_openai_chat_with_tools)

    resp = client.post("/api/ai/chat", json={"account_id": "default", "message": "show my profile"})
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("assistant_message")
    assert body.get("tool_calls") and body["tool_calls"][0]["status"] == "blocked"
