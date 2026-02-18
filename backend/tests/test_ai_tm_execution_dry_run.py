from __future__ import annotations

import os
from datetime import UTC, datetime

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.schemas.ai_trading_manager import BrokerSnapshot, LedgerSnapshot, Quote, TradeIntent, TradePlan
from app.services.ai_trading_manager.execution.engine import ExecutionEngine
from app.services.ai_trading_manager.riskgate.engine import evaluate_riskgate


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_AI_ASSISTANT_ENABLED"] = "1"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_execution_dry_run_returns_deterministic_order_intents() -> None:
    ts = datetime(2026, 2, 18, 10, 0, 0, tzinfo=UTC)
    plan = TradePlan(
        plan_id="plan-1",
        intent=TradeIntent(
            symbols=["SBIN", "INFY"],
            side="BUY",
            product="CNC",
            constraints={"qty": 2},
            risk_budget_pct=0.5,
        ),
        order_skeleton={"order_type": "MARKET"},
    )
    broker = BrokerSnapshot(
        as_of_ts=ts,
        account_id="default",
        source="stub",
        quotes_cache=[
            Quote(symbol="SBIN", last_price=700.0, as_of_ts=ts),
            Quote(symbol="INFY", last_price=1500.0, as_of_ts=ts),
        ],
    )
    ledger = LedgerSnapshot(as_of_ts=ts, account_id="default")

    risk = evaluate_riskgate(plan=plan, broker=broker, ledger=ledger, eval_ts=ts).decision
    assert risk.outcome.value == "allow"

    engine_exec = ExecutionEngine()
    with SessionLocal() as db:
        res = engine_exec.dry_run_execute(
            db,
            user_id=None,
            account_id="default",
            correlation_id="corr-1",
            plan=plan,
            idempotency_key="idem-1",
        )
        assert res.idempotency_record_id
        assert [o["symbol"] for o in res.order_intents] == ["INFY", "SBIN"]
        assert all(o["qty"] == 2.0 for o in res.order_intents)

