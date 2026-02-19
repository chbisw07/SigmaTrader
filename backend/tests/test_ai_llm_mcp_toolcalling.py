from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import Candle
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


def _login_user() -> None:
    # Create a real session cookie so attachment endpoints can validate access.
    client.post(
        "/api/auth/register",
        json={"username": "att_user", "password": "pw12345", "display_name": "Att"},
    )
    resp = client.post("/api/auth/login", json={"username": "att_user", "password": "pw12345"})
    client.cookies.clear()
    client.cookies.update(resp.cookies)


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
                        "name": "cancel_order",
                        "description": "Cancel order",
                        "inputSchema": {"type": "object", "properties": {"order_id": {"type": "string"}}},
                        "annotations": {"readOnlyHint": False, "destructiveHint": True},
                    },
                ]
            }

        async def tools_call(self, *, name: str, arguments: dict):  # noqa: ARG002
            if name == "get_profile":
                return {"content": [{"type": "text", "text": "{\"user_id\":\"CZC754\"}"}], "isError": False}
            if name == "get_holdings":
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "["
                                "{\"tradingsymbol\":\"INFY\",\"quantity\":14,\"average_price\":1384.2,\"last_price\":1370.5,\"pnl\":-191.8},"
                                "{\"tradingsymbol\":\"TCS\",\"quantity\":4,\"average_price\":4000,\"last_price\":4050,\"pnl\":200},"
                                "{\"tradingsymbol\":\"RELIANCE\",\"quantity\":14,\"average_price\":1415.6,\"last_price\":1409.5,\"pnl\":-85.4}"
                                "]"
                            ),
                        }
                    ],
                    "isError": False,
                }
            if name == "get_positions":
                return {"content": [{"type": "text", "text": "{\"net\": []}"}], "isError": False}
            if name == "get_orders":
                return {"content": [{"type": "text", "text": "[]"}], "isError": False}
            if name == "get_margins":
                # Provide equity for sizing.
                return {"content": [{"type": "text", "text": "{\"equity\": 100000}"}], "isError": False}
            if name == "place_order":
                return {"content": [{"type": "text", "text": "{\"order_id\":\"oid-1\"}"}], "isError": False}
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


def _seed_candles(symbol: str, *, days: int = 20) -> None:
    # Seed deterministic daily candles so ATR sizing works.
    from datetime import UTC, datetime, timedelta

    now = datetime(2026, 2, 18, 10, 0, 0, tzinfo=UTC)
    with SessionLocal() as db:
        for i in range(days):
            ts = now - timedelta(days=(days - i))
            # Simple rising candles.
            o = 700.0 + i
            h = o + 5.0
            low = o - 5.0
            c = o + 1.0
            db.add(
                Candle(
                    symbol=symbol,
                    exchange="NSE",
                    timeframe="1d",
                    ts=ts,
                    open=o,
                    high=h,
                    low=low,
                    close=c,
                    volume=1000.0,
                )
            )
        db.commit()


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


def test_chat_stream_emits_events(monkeypatch: pytest.MonkeyPatch, fake_kite_mcp) -> None:
    _enable_ai_provider(monkeypatch)

    events: list[dict] = []
    with client.stream(
        "POST",
        "/api/ai/chat/stream",
        json={"account_id": "default", "thread_id": "default", "message": "fetch my top 5 holdings"},
    ) as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if not line:
                continue
            ev = json.loads(line)
            events.append(ev)
            if ev.get("type") in {"done", "error"}:
                break

    assert any(e.get("type") == "decision" and e.get("decision_id") for e in events)
    assert any(e.get("type") == "assistant_delta" for e in events)
    assert any(e.get("type") == "done" and e.get("assistant_message") for e in events)


def test_chat_with_attachments_records_trace(monkeypatch: pytest.MonkeyPatch, fake_kite_mcp) -> None:
    _enable_ai_provider(monkeypatch)
    _login_user()

    # Upload a tiny CSV attachment.
    files = [("files", ("pnl.csv", b"symbol,pnl\nABC,10\n", "text/csv"))]
    up = client.post("/api/ai/files", files=files)
    assert up.status_code == 200
    file_id = up.json()["files"][0]["file_id"]

    resp = client.post(
        "/api/ai/chat",
        json={
            "account_id": "default",
            "message": "fetch my top 5 holdings",
            "attachments": [{"file_id": file_id, "how": "auto"}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()

    tr = client.get(f"/api/ai/decision-traces/{body['decision_id']}")
    assert tr.status_code == 200
    inputs = tr.json().get("inputs_used") or {}
    atts = inputs.get("attachments") or []
    assert isinstance(atts, list)
    assert any(a.get("file_id") == file_id for a in atts)

    thread = client.get("/api/ai/thread?account_id=default&thread_id=default")
    assert thread.status_code == 200
    msgs = thread.json().get("messages") or []
    user_msgs = [m for m in msgs if m.get("role") == "user"]
    assert user_msgs and any((m.get("attachments") or []) for m in user_msgs)


def test_chat_direct_show_holdings_returns_full_table(monkeypatch: pytest.MonkeyPatch, fake_kite_mcp) -> None:
    _enable_ai_provider(monkeypatch)

    # Ensure LLM isn't called for direct portfolio display.
    from app.services.ai_toolcalling import orchestrator as orch

    async def _boom(*a, **k):  # noqa: ANN001
        raise AssertionError("openai_chat_with_tools should not be called for direct show holdings")

    monkeypatch.setattr(orch, "openai_chat_with_tools", _boom)

    resp = client.post("/api/ai/chat", json={"account_id": "default", "message": "Show my holdings (CNC)"})
    assert resp.status_code == 200
    body = resp.json()
    text = body["assistant_message"]
    assert "Holdings (Delivery/CNC) — 3" in text
    assert "| Symbol |" in text
    assert "INFY" in text and "TCS" in text and "RELIANCE" in text


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


def test_chat_trade_propose_then_execute(monkeypatch: pytest.MonkeyPatch, fake_kite_mcp) -> None:
    _enable_ai_provider(monkeypatch)
    _seed_candles("SBIN", days=20)

    # Mark MCP connected (required to enable execution).
    st = client.get("/api/mcp/kite/status")
    assert st.status_code == 200

    # Enable execution flag now that MCP is connected.
    upd = client.put("/api/settings/ai", json={"feature_flags": {"ai_execution_enabled": True}})
    assert upd.status_code == 200

    from app.services.ai_toolcalling import orchestrator as orch
    from app.services.ai_toolcalling.openai_toolcaller import OpenAiAssistantTurn, OpenAiToolCall

    calls = {"n": 0}

    async def fake_openai_chat_with_tools(*, api_key, model, messages, tools, **kwargs):  # noqa: ANN001
        calls["n"] += 1
        if calls["n"] == 1:
            return OpenAiAssistantTurn(
                content="",
                tool_calls=[
                    OpenAiToolCall(
                        tool_call_id="tp1",
                        name="propose_trade_plan",
                        arguments={
                            "symbols": ["SBIN"],
                            "side": "BUY",
                            "product": "MIS",
                            "risk_budget_pct": 0.5,
                            "atr_period": 14,
                            "atr_multiplier": 2.0,
                        },
                    )
                ],
                raw={},
            )
        if calls["n"] == 2:
            # Pull plan_id from the last tool response content.
            plan_id = None
            for m in reversed(messages):
                if m.get("role") == "tool":
                    try:
                        payload = json.loads(m.get("content") or "{}")
                        plan_id = ((payload.get("plan") or {}) or {}).get("plan_id")
                    except Exception:
                        pass
                    break
            return OpenAiAssistantTurn(
                content="",
                tool_calls=[
                    OpenAiToolCall(
                        tool_call_id="ex1",
                        name="execute_trade_plan",
                        arguments={"plan_id": plan_id},
                    )
                ],
                raw={},
            )
        return OpenAiAssistantTurn(
            content="Executed. Order placed and reconciled.",
            tool_calls=[],
            raw={},
        )

    monkeypatch.setattr(orch, "openai_chat_with_tools", fake_openai_chat_with_tools)

    resp = client.post(
        "/api/ai/chat",
        json={"account_id": "default", "message": "Buy SBIN MIS risk 0.5% with ATR stop"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision_id"]
    tr = client.get(f"/api/ai/decision-traces/{body['decision_id']}")
    assert tr.status_code == 200
    trace = tr.json()
    assert trace["final_outcome"].get("trade_plan")
    assert trace["final_outcome"].get("execution")
