from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.schemas.ai_trading_manager import (
    BrokerSnapshot,
    LedgerSnapshot,
    Quote,
    TradeIntent,
    TradePlan,
)
from app.services.ai_trading_manager.riskgate.engine import evaluate_riskgate
from app.services.ai_trading_manager.riskgate.policy_config import RiskPolicyConfig


def _fixed_ts() -> datetime:
    return datetime(2026, 2, 18, 10, 0, 0, tzinfo=UTC)


def test_riskgate_is_deterministic_for_same_inputs() -> None:
    ts = _fixed_ts()
    plan = TradePlan(
        plan_id="p1",
        intent=TradeIntent(symbols=["INFY"], side="BUY", product="CNC", constraints={}, risk_budget_pct=0.5),
        order_skeleton={"order_type": "MARKET"},
    )
    broker = BrokerSnapshot(
        as_of_ts=ts,
        account_id="default",
        source="stub",
        quotes_cache=[Quote(symbol="INFY", last_price=1500.0, as_of_ts=ts)],
    )
    ledger = LedgerSnapshot(as_of_ts=ts, account_id="default")
    policy = RiskPolicyConfig(max_per_trade_risk_pct=1.0, quote_max_age_sec=10)

    r1 = evaluate_riskgate(plan=plan, broker=broker, ledger=ledger, policy=policy, eval_ts=ts).decision
    r2 = evaluate_riskgate(plan=plan, broker=broker, ledger=ledger, policy=policy, eval_ts=ts).decision
    assert r1.model_dump(mode="json") == r2.model_dump(mode="json")


def test_riskgate_denies_stale_quote() -> None:
    ts = _fixed_ts()
    stale = ts - timedelta(seconds=60)
    plan = TradePlan(
        plan_id="p2",
        intent=TradeIntent(symbols=["SBIN"], side="BUY", product="CNC", constraints={}, risk_budget_pct=0.5),
        order_skeleton={"order_type": "MARKET"},
    )
    broker = BrokerSnapshot(
        as_of_ts=ts,
        account_id="default",
        source="stub",
        quotes_cache=[Quote(symbol="SBIN", last_price=700.0, as_of_ts=stale)],
    )
    ledger = LedgerSnapshot(as_of_ts=ts, account_id="default")
    policy = RiskPolicyConfig(quote_max_age_sec=10)

    decision = evaluate_riskgate(plan=plan, broker=broker, ledger=ledger, policy=policy, eval_ts=ts).decision
    assert decision.outcome.value == "deny"
    assert any(r.startswith("QUOTE_STALE:SBIN") for r in decision.reasons)


def test_riskgate_denies_risk_budget_over_max() -> None:
    ts = _fixed_ts()
    plan = TradePlan(
        plan_id="p3",
        intent=TradeIntent(symbols=["TCS"], side="BUY", product="CNC", constraints={}, risk_budget_pct=5.0),
        order_skeleton={"order_type": "MARKET"},
    )
    broker = BrokerSnapshot(
        as_of_ts=ts,
        account_id="default",
        source="stub",
        quotes_cache=[Quote(symbol="TCS", last_price=4000.0, as_of_ts=ts)],
    )
    ledger = LedgerSnapshot(as_of_ts=ts, account_id="default")
    policy = RiskPolicyConfig(max_per_trade_risk_pct=1.0)

    decision = evaluate_riskgate(plan=plan, broker=broker, ledger=ledger, policy=policy, eval_ts=ts).decision
    assert decision.outcome.value == "deny"
    assert "RISK_BUDGET_EXCEEDS_MAX" in decision.reasons

