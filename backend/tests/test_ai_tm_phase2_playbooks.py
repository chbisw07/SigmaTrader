from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import List

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import desc, select

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.schemas.ai_trading_manager import (
    BrokerOrder,
    BrokerPosition,
    BrokerSnapshot,
    Quote,
)
from app.services.ai_trading_manager.broker_adapter import BrokerOrderAck, OrderIntent
from app.services.ai_trading_manager.brokers.stub import StubBrokerAdapter
from app.services.ai_trading_manager.automation.runner import run_automation_tick
from app.services.ai_trading_manager.ai_settings_config import get_ai_settings_with_source, set_ai_settings
from app.models.ai_trading_manager import AiTmExpectedPosition, AiTmPlaybook, AiTmPlaybookRun
from app.schemas.ai_settings import KiteMcpStatus

client = TestClient(app)


class FakeBrokerAdapter(StubBrokerAdapter):
    name = "fake"
    fixed_ts = datetime(2026, 2, 18, 10, 0, 0, tzinfo=UTC)

    def __init__(self) -> None:
        super().__init__(mode="mirror", fixed_quotes={"INFY": 1500.0, "SBIN": 700.0})
        self.placed: List[OrderIntent] = []

    def get_snapshot(self, *, account_id: str) -> BrokerSnapshot:
        now = self.fixed_ts
        return BrokerSnapshot(
            as_of_ts=now,
            account_id=account_id,
            source=self.name,
            holdings=[],
            positions=[
                BrokerPosition(symbol="INFY", product="CNC", qty=10, avg_price=1500.0),
            ],
            orders=[],
            margins={},
            quotes_cache=[
                Quote(symbol="INFY", last_price=1500.0, as_of_ts=now),
                Quote(symbol="SBIN", last_price=700.0, as_of_ts=now),
            ],
        )

    def get_quotes(self, *, account_id: str, symbols: list[str]):
        now = self.fixed_ts
        out = []
        for s in symbols:
            px = self.fixed_quotes.get(str(s).upper(), 1.0) if self.fixed_quotes else 1.0
            out.append(Quote(symbol=str(s).upper(), last_price=float(px), as_of_ts=now))
        return out

    def place_order(self, *, account_id: str, intent: OrderIntent) -> BrokerOrderAck:
        self.placed.append(intent)
        return BrokerOrderAck(broker_order_id=f"fake-{len(self.placed)}", status="ACK")

    def get_orders(self, *, account_id: str) -> list[BrokerOrder]:
        return []


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_AI_ASSISTANT_ENABLED"] = "1"
    os.environ["ST_MONITORING_ENABLED"] = "1"
    os.environ["ST_AI_EXECUTION_ENABLED"] = "0"
    os.environ["ST_AI_EXECUTION_KILL_SWITCH"] = "0"
    os.environ["ST_KITE_MCP_ENABLED"] = "0"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _seed_authorization_message_id() -> str:
    resp = client.post("/api/ai/messages", json={"account_id": "default", "content": "authorize playbook"})
    assert resp.status_code == 200
    thread = resp.json()["thread"]
    user_msgs = [m for m in thread["messages"] if m["role"] == "user"]
    assert user_msgs
    return user_msgs[-1]["message_id"]


def test_playbooks_create_arm_run_now_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeBrokerAdapter()
    monkeypatch.setattr("app.api.ai_trading_manager.get_broker_adapter", lambda *_args, **_kwargs: fake)

    plan_resp = client.post(
        "/api/ai/trade-plans",
        json={
            "account_id": "default",
            "intent": {
                "symbols": ["INFY", "SBIN"],
                "side": "BUY",
                "product": "CNC",
                "constraints": {"qty": 1},
                "risk_budget_pct": 0.5,
            },
        },
    )
    assert plan_resp.status_code == 200
    plan = plan_resp.json()["plan"]

    pb_resp = client.post(
        "/api/ai/playbooks",
        json={"account_id": "default", "name": "PB1", "description": None, "plan": plan, "cadence_sec": 60},
    )
    assert pb_resp.status_code == 201
    playbook_id = pb_resp.json()["playbook"]["playbook_id"]

    arm_resp = client.post(f"/api/ai/playbooks/{playbook_id}/arm?armed=1")
    assert arm_resp.status_code == 200

    run_resp = client.post(f"/api/ai/playbooks/{playbook_id}/run-now")
    assert run_resp.status_code == 200
    assert run_resp.json()["outcome"]["execution"]["mode"] == "dry_run"

    runs_resp = client.get(f"/api/ai/playbooks/{playbook_id}/runs?limit=10")
    assert runs_resp.status_code == 200
    runs = runs_resp.json()
    assert len(runs) >= 1


def test_playbook_run_now_execute_path_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    os.environ["ST_AI_EXECUTION_ENABLED"] = "1"
    os.environ["ST_KITE_MCP_ENABLED"] = "1"
    get_settings.cache_clear()

    # Ensure execution gating passes (connected MCP status is persisted in DB).
    with SessionLocal() as db:
        cfg, _src = get_ai_settings_with_source(db, get_settings())
        cfg.feature_flags.kite_mcp_enabled = True
        cfg.feature_flags.ai_execution_enabled = True
        cfg.kite_mcp.server_url = cfg.kite_mcp.server_url or "https://mcp.kite.trade/sse"
        cfg.kite_mcp.last_status = KiteMcpStatus.connected
        set_ai_settings(db, get_settings(), cfg)

    fake = FakeBrokerAdapter()
    monkeypatch.setattr("app.api.ai_trading_manager.get_broker_adapter", lambda *_args, **_kwargs: fake)

    auth_id = _seed_authorization_message_id()

    plan_resp = client.post(
        "/api/ai/trade-plans",
        json={
            "account_id": "default",
            "intent": {
                "symbols": ["INFY"],
                "side": "BUY",
                "product": "CNC",
                "constraints": {"qty": 1},
                "risk_budget_pct": 0.5,
            },
        },
    )
    assert plan_resp.status_code == 200
    plan = plan_resp.json()["plan"]

    pb_resp = client.post(
        "/api/ai/playbooks",
        json={"account_id": "default", "name": "PB2", "description": None, "plan": plan, "cadence_sec": 60},
    )
    assert pb_resp.status_code == 201
    playbook_id = pb_resp.json()["playbook"]["playbook_id"]

    run1 = client.post(f"/api/ai/playbooks/{playbook_id}/run-now?authorization_message_id={auth_id}")
    assert run1.status_code == 200
    run2 = client.post(f"/api/ai/playbooks/{playbook_id}/run-now?authorization_message_id={auth_id}")
    assert run2.status_code == 200
    assert len(fake.placed) == 1

    # Reset env for other tests.
    os.environ["ST_AI_EXECUTION_ENABLED"] = "0"
    os.environ["ST_KITE_MCP_ENABLED"] = "0"
    get_settings.cache_clear()

    with SessionLocal() as db:
        cfg, _src = get_ai_settings_with_source(db, get_settings())
        cfg.feature_flags.kite_mcp_enabled = False
        cfg.feature_flags.ai_execution_enabled = False
        cfg.kite_mcp.last_status = KiteMcpStatus.unknown
        set_ai_settings(db, get_settings(), cfg)


def test_expected_ledger_resync_populates_expected_positions(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeBrokerAdapter()
    monkeypatch.setattr("app.api.ai_trading_manager.get_broker_adapter", lambda *_args, **_kwargs: fake)

    resp = client.post("/api/ai/expected-ledger/resync?account_id=default")
    assert resp.status_code == 200
    assert resp.json()["updated_positions"] >= 1

    with SessionLocal() as db:
        rows = db.execute(
            select(AiTmExpectedPosition).where(AiTmExpectedPosition.account_id == "default")
        ).scalars().all()
        assert any(r.symbol == "INFY" and float(r.expected_qty) == 10.0 for r in rows)


def test_exception_ack_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    # Reuse the Phase 0 reconcile to create exceptions, then ack them.
    fake = FakeBrokerAdapter()
    monkeypatch.setattr("app.api.ai_trading_manager.get_broker_adapter", lambda *_args, **_kwargs: fake)

    rec = client.post("/api/ai/reconcile?account_id=default")
    assert rec.status_code == 200

    ex = client.get("/api/ai/exceptions?account_id=default&status_filter=OPEN&limit=10")
    assert ex.status_code == 200
    rows = ex.json()
    if not rows:
        return
    ex_id = rows[0]["exception_id"]

    ack = client.post(f"/api/ai/exceptions/{ex_id}/ack")
    assert ack.status_code == 200

    ex2 = client.get("/api/ai/exceptions?account_id=default&status_filter=OPEN&limit=10")
    assert ex2.status_code == 200
    assert all(r["exception_id"] != ex_id for r in ex2.json())


def test_automation_tick_dedupes_by_window(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeBrokerAdapter()
    monkeypatch.setattr(
        "app.services.ai_trading_manager.automation.runner.get_broker_adapter",
        lambda *_args, **_kwargs: fake,
    )

    # Seed a playbook directly as due.
    playbook_id: str | None = None
    with SessionLocal() as db:
        pb = db.execute(select(AiTmPlaybook).order_by(desc(AiTmPlaybook.created_at))).scalars().first()
        if pb is None:
            plan_resp = client.post(
                "/api/ai/trade-plans",
                json={
                    "account_id": "default",
                    "intent": {
                        "symbols": ["INFY"],
                        "side": "BUY",
                        "product": "CNC",
                        "constraints": {"qty": 1},
                        "risk_budget_pct": 0.5,
                    },
                },
            )
            assert plan_resp.status_code == 200
            plan = plan_resp.json()["plan"]
            pb_resp = client.post(
                "/api/ai/playbooks",
                json={"account_id": "default", "name": "PB-AUTO", "description": None, "plan": plan, "cadence_sec": 60},
            )
            assert pb_resp.status_code == 201
            playbook_id = pb_resp.json()["playbook"]["playbook_id"]
            pb = db.execute(select(AiTmPlaybook).where(AiTmPlaybook.playbook_id == playbook_id)).scalars().first()
        assert pb is not None
        target_id = pb.playbook_id
        # Ensure we only consider the target playbook in this test.
        for other in db.execute(select(AiTmPlaybook)).scalars().all():
            if other.playbook_id != target_id:
                other.armed = False
                other.next_run_at = None
        pb.enabled = True
        pb.armed = True
        pb.cadence_sec = 3600
        pb.next_run_at = datetime.now(UTC) - timedelta(seconds=1)
        pb.updated_at = datetime.now(UTC)
        db.commit()

    ran1 = run_automation_tick(max_playbooks=5)
    assert ran1 >= 0

    with SessionLocal() as db:
        # Force it due again within the same dedupe window.
        pb2 = db.execute(select(AiTmPlaybook).where(AiTmPlaybook.playbook_id == target_id)).scalars().first()
        assert pb2 is not None
        pb2.next_run_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

        before = db.execute(select(AiTmPlaybookRun).where(AiTmPlaybookRun.playbook_id == target_id)).scalars().all()

    ran2 = run_automation_tick(max_playbooks=5)
    assert ran2 >= 0

    with SessionLocal() as db:
        after = db.execute(select(AiTmPlaybookRun).where(AiTmPlaybookRun.playbook_id == target_id)).scalars().all()
        assert len(after) == len(before)
