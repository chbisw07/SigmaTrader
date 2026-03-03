from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import Candle


client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_AI_ASSISTANT_ENABLED"] = "1"
    os.environ["ST_AI_EXECUTION_KILL_SWITCH"] = "0"
    os.environ["ST_CRYPTO_KEY"] = "test-ai-hybrid-secret"
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


def _seed_candles(symbol: str, *, days: int = 20) -> None:
    from datetime import UTC, datetime, timedelta

    now = datetime(2026, 2, 18, 10, 0, 0, tzinfo=UTC)
    with SessionLocal() as db:
        # Keep idempotent across tests.
        db.query(Candle).filter(Candle.symbol == symbol, Candle.exchange == "NSE", Candle.timeframe == "1d").delete()
        for i in range(days):
            ts = now - timedelta(days=(days - i))
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


@pytest.fixture()
def fake_kite_mcp_hybrid(monkeypatch: pytest.MonkeyPatch):
    # Enable Kite MCP + hybrid gateway toggles.
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
                        "name": "get_ltp",
                        "description": "Return LTP",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"symbols": {"type": "array", "items": {"type": "string"}}},
                            "required": ["symbols"],
                            "additionalProperties": False,
                        },
                        "annotations": {"readOnlyHint": True, "destructiveHint": False},
                    },
                    {
                        "name": "get_holdings",
                        "description": "Return holdings",
                        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                        "annotations": {"readOnlyHint": True, "destructiveHint": False},
                    },
                    {
                        "name": "get_positions",
                        "description": "Return positions",
                        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                        "annotations": {"readOnlyHint": True, "destructiveHint": False},
                    },
                    {
                        "name": "get_orders",
                        "description": "Return orders",
                        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                        "annotations": {"readOnlyHint": True, "destructiveHint": False},
                    },
                    {
                        "name": "get_margins",
                        "description": "Return margins",
                        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                        "annotations": {"readOnlyHint": True, "destructiveHint": False},
                    },
                    {
                        "name": "get_profile",
                        "description": "Return profile",
                        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                        "annotations": {"readOnlyHint": True, "destructiveHint": False},
                    },
                    {
                        "name": "place_order",
                        "description": "Place order",
                        "inputSchema": {"type": "object", "properties": {"tradingsymbol": {"type": "string"}}, "additionalProperties": True},
                        "annotations": {"readOnlyHint": False, "destructiveHint": True},
                    },
                ]
            }

        async def tools_call(self, *, name: str, arguments: dict):  # noqa: ARG002
            calls[name] = calls.get(name, 0) + 1
            if name == "get_profile":
                return {"content": [{"type": "text", "text": "{\"user_id\":\"CZC754\",\"email\":\"a@example.com\"}"}], "isError": False}
            if name == "get_ltp":
                return {"content": [{"type": "text", "text": "{\"NSE:INFY\":{\"last_price\":1370.5}}"}], "isError": False}
            if name == "get_holdings":
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "[{\"tradingsymbol\":\"INFY\",\"quantity\":14,\"average_price\":1384.2,\"last_price\":1370.5,\"pnl\":-191.8}]",
                        }
                    ],
                    "isError": False,
                }
            if name == "get_positions":
                return {"content": [{"type": "text", "text": "{\"net\": []}"}], "isError": False}
            if name == "get_orders":
                return {"content": [{"type": "text", "text": "[]"}], "isError": False}
            if name == "get_margins":
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

    return calls


def _extract_last_toolresult(messages: list[dict]) -> dict | None:
    for m in reversed(messages or []):
        if m.get("role") != "user":
            continue
        c = str(m.get("content") or "")
        if "ToolResult (json):" not in c:
            continue
        raw = c.split("ToolResult (json):", 1)[1].strip()
        try:
            return json.loads(raw)
        except Exception:
            i = raw.find("{")
            j = raw.rfind("}")
            if i >= 0 and j > i:
                try:
                    return json.loads(raw[i : j + 1])
                except Exception:
                    return None
            return None
    return None


def test_hybrid_remote_tool_loop_market_data(monkeypatch: pytest.MonkeyPatch, fake_kite_mcp_hybrid) -> None:
    _enable_ai_provider()

    from app.services.ai_toolcalling import orchestrator as orch
    from app.services.ai_toolcalling.openai_toolcaller import OpenAiAssistantTurn

    calls = {"n": 0}

    async def fake_openai_chat_plain(*, api_key, model, messages, **kwargs):  # noqa: ANN001, ARG001
        calls["n"] += 1
        if calls["n"] == 1:
            return OpenAiAssistantTurn(
                content=json.dumps(
                    {
                        "tool_requests": [
                            {
                                "request_id": "r1",
                                "tool_name": "get_ltp",
                                "args": {"symbols": ["NSE:INFY"]},
                                "reason": "need current price",
                                "risk_tier": "LOW",
                            }
                        ]
                    }
                ),
                tool_calls=[],
                raw={},
            )
        return OpenAiAssistantTurn(content=json.dumps({"final_message": "INFY LTP fetched."}), tool_calls=[], raw={})

    monkeypatch.setattr(orch, "openai_chat_plain", fake_openai_chat_plain)

    resp = client.post("/api/ai/chat", json={"account_id": "default", "message": "What is INFY LTP?"})
    assert resp.status_code == 200
    body = resp.json()
    assert "LTP" in body["assistant_message"] or body["assistant_message"]
    assert any(t["name"] == "get_ltp" for t in body["tool_calls"])


def test_hybrid_exfiltration_denied_and_audited(monkeypatch: pytest.MonkeyPatch, fake_kite_mcp_hybrid) -> None:
    _enable_ai_provider()

    from app.services.ai_toolcalling import orchestrator as orch
    from app.services.ai_toolcalling.openai_toolcaller import OpenAiAssistantTurn

    calls = {"n": 0}

    async def fake_openai_chat_plain(*, api_key, model, messages, **kwargs):  # noqa: ANN001, ARG001
        calls["n"] += 1
        if calls["n"] == 1:
            return OpenAiAssistantTurn(
                content=json.dumps(
                    {
                        "tool_requests": [
                            {"request_id": "x1", "tool_name": "get_profile", "args": {}, "reason": "identity", "risk_tier": "HIGH"}
                        ]
                    }
                ),
                tool_calls=[],
                raw={},
            )
        return OpenAiAssistantTurn(content=json.dumps({"final_message": "Cannot access profile."}), tool_calls=[], raw={})

    monkeypatch.setattr(orch, "openai_chat_plain", fake_openai_chat_plain)

    resp = client.post("/api/ai/chat", json={"account_id": "default", "message": "Show my profile"})
    assert resp.status_code == 200
    body = resp.json()
    # LSG denial shows up as a tool call entry.
    assert any(t["name"] == "get_profile" and t["status"] in {"blocked", "error"} for t in body["tool_calls"])
    # Ensure the fake MCP get_profile tool was never executed.
    assert fake_kite_mcp_hybrid.get("get_profile", 0) == 0


def test_hybrid_e2e_smoke_no_broker_write_when_execution_disabled(monkeypatch: pytest.MonkeyPatch, fake_kite_mcp_hybrid) -> None:
    _enable_ai_provider()
    _seed_candles("SBIN", days=20)

    from app.services.ai_toolcalling import orchestrator as orch
    from app.services.ai_toolcalling.openai_toolcaller import OpenAiAssistantTurn

    calls = {"n": 0}

    async def fake_openai_chat_plain(*, api_key, model, messages, **kwargs):  # noqa: ANN001, ARG001
        calls["n"] += 1
        if calls["n"] == 1:
            return OpenAiAssistantTurn(
                content=json.dumps(
                    {
                        "tool_requests": [
                            {"request_id": "m1", "tool_name": "get_ltp", "args": {"symbols": ["NSE:SBIN"]}, "reason": "price", "risk_tier": "LOW"}
                        ]
                    }
                ),
                tool_calls=[],
                raw={},
            )
        if calls["n"] == 2:
            return OpenAiAssistantTurn(
                content=json.dumps(
                    {
                        "tool_requests": [
                            {
                                "request_id": "p1",
                                "tool_name": "propose_trade_plan",
                                "args": {
                                    "symbols": ["SBIN"],
                                    "side": "BUY",
                                    "product": "MIS",
                                    "risk_budget_pct": 0.5,
                                    "atr_period": 14,
                                    "atr_multiplier": 2.0,
                                },
                                "reason": "create plan",
                                "risk_tier": "MED",
                            }
                        ]
                    }
                ),
                tool_calls=[],
                raw={},
            )
        if calls["n"] == 3:
            tr = _extract_last_toolresult(messages)
            plan_id = None
            if isinstance(tr, dict):
                data = tr.get("data") if isinstance(tr.get("data"), dict) else {}
                plan_id = data.get("plan_id") or (data.get("plan") or {}).get("plan_id")
            return OpenAiAssistantTurn(
                content=json.dumps(
                    {
                        "tool_requests": [
                            {"request_id": "e1", "tool_name": "execute_trade_plan", "args": {"plan_id": plan_id}, "reason": "try execute", "risk_tier": "HIGH"}
                        ]
                    }
                ),
                tool_calls=[],
                raw={},
            )
        return OpenAiAssistantTurn(
            content=json.dumps({"final_message": "Proposed plan and evaluated execution."}),
            tool_calls=[],
            raw={},
        )

    monkeypatch.setattr(orch, "openai_chat_plain", fake_openai_chat_plain)

    # Execution disabled by default. Ensure no place_order tool is invoked.
    resp = client.post("/api/ai/chat", json={"account_id": "default", "message": "Execute buy SBIN MIS risk 0.5% with ATR stop"})
    assert resp.status_code == 200
    body = resp.json()
    assert any(t["name"] == "get_ltp" for t in body["tool_calls"])
    assert any(t["name"] == "propose_trade_plan" for t in body["tool_calls"])
    assert any(t["name"] == "execute_trade_plan" for t in body["tool_calls"])
    assert fake_kite_mcp_hybrid.get("place_order", 0) == 0


def test_hybrid_e2e_smoke_exec_enabled_routes_broker_write_via_same_path(monkeypatch: pytest.MonkeyPatch, fake_kite_mcp_hybrid) -> None:
    _enable_ai_provider()
    _seed_candles("SBIN", days=20)

    # Make RiskGate deterministic in tests (avoid market-hours dependence).
    monkeypatch.setattr(
        "app.services.ai_trading_manager.riskgate.rules_market.evaluate_market_hours",
        lambda *a, **k: [],
    )
    # Force RiskGate to allow in this smoke test so we can assert broker-write routing deterministically.
    from types import SimpleNamespace
    from app.schemas.ai_trading_manager import RiskDecision, RiskDecisionOutcome

    monkeypatch.setattr(
        "app.services.ai_toolcalling.orchestrator.evaluate_riskgate",
        lambda **kwargs: SimpleNamespace(decision=RiskDecision(outcome=RiskDecisionOutcome.allow)),
    )

    # Mark MCP connected (required to enable execution).
    st = client.get("/api/mcp/kite/status")
    assert st.status_code == 200

    upd = client.put("/api/settings/ai", json={"feature_flags": {"ai_execution_enabled": True}})
    assert upd.status_code == 200

    from app.services.ai_toolcalling import orchestrator as orch
    from app.services.ai_toolcalling.openai_toolcaller import OpenAiAssistantTurn

    calls = {"n": 0}

    async def fake_openai_chat_plain(*, api_key, model, messages, **kwargs):  # noqa: ANN001, ARG001
        calls["n"] += 1
        if calls["n"] == 1:
            return OpenAiAssistantTurn(
                content=json.dumps(
                    {
                        "tool_requests": [
                            {"request_id": "p1", "tool_name": "propose_trade_plan", "args": {"symbols": ["SBIN"], "side": "BUY", "product": "MIS"}, "reason": "plan", "risk_tier": "MED"}
                        ]
                    }
                ),
                tool_calls=[],
                raw={},
            )
        if calls["n"] == 2:
            tr = _extract_last_toolresult(messages)
            plan_id = None
            if isinstance(tr, dict):
                data = tr.get("data") if isinstance(tr.get("data"), dict) else {}
                plan_id = data.get("plan_id") or (data.get("plan") or {}).get("plan_id")
            return OpenAiAssistantTurn(
                content=json.dumps({"tool_requests": [{"request_id": "e1", "tool_name": "execute_trade_plan", "args": {"plan_id": plan_id}, "reason": "execute", "risk_tier": "HIGH"}]}),
                tool_calls=[],
                raw={},
            )
        return OpenAiAssistantTurn(content=json.dumps({"final_message": "Executed."}), tool_calls=[], raw={})

    monkeypatch.setattr(orch, "openai_chat_plain", fake_openai_chat_plain)

    resp = client.post("/api/ai/chat", json={"account_id": "default", "message": "Go ahead and execute buy SBIN MIS now"})
    assert resp.status_code == 200
    body = resp.json()
    assert any(t["name"] == "execute_trade_plan" for t in body["tool_calls"])
    tr = client.get(f"/api/ai/decision-traces/{body['decision_id']}")
    assert tr.status_code == 200
    assert "execute" in str(tr.json().get("user_message") or "").lower()
    exec_out = (tr.json().get("final_outcome") or {}).get("execution") or {}
    assert exec_out.get("executed") is True, exec_out
    assert fake_kite_mcp_hybrid.get("place_order", 0) >= 1
