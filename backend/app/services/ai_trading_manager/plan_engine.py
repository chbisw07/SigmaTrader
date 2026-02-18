from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.schemas.ai_trading_manager import TradeIntent, TradePlan


def normalize_intent(intent: TradeIntent) -> TradeIntent:
    symbols = sorted({str(s).strip().upper() for s in intent.symbols if str(s).strip()})
    return TradeIntent(
        symbols=symbols,
        side=str(intent.side).strip().upper(),  # type: ignore[arg-type]
        product=str(intent.product).strip().upper(),  # type: ignore[arg-type]
        constraints=dict(intent.constraints or {}),
        risk_budget_pct=intent.risk_budget_pct,
    )


def normalize_trade_plan(plan: TradePlan) -> TradePlan:
    plan_id = str(plan.plan_id).strip() or uuid4().hex
    intent = normalize_intent(plan.intent)
    order_skeleton = dict(plan.order_skeleton or {})
    if "order_type" in order_skeleton:
        order_skeleton["order_type"] = str(order_skeleton["order_type"]).strip().upper()
    else:
        order_skeleton["order_type"] = "MARKET"

    return TradePlan(
        plan_id=plan_id,
        intent=intent,
        entry_rules=list(plan.entry_rules or []),
        sizing_method=str(plan.sizing_method or "fixed"),
        risk_model=dict(plan.risk_model or {}),
        order_skeleton=order_skeleton,
        validity_window=dict(plan.validity_window or {}),
        idempotency_scope=str(plan.idempotency_scope or "account"),
    )


def new_plan_from_intent(intent: TradeIntent) -> TradePlan:
    norm = normalize_intent(intent)
    return TradePlan(
        plan_id=uuid4().hex,
        intent=norm,
        entry_rules=[],
        sizing_method="fixed",
        risk_model={},
        order_skeleton={"order_type": "MARKET"},
        validity_window={},
        idempotency_scope="account",
    )


def utcnow() -> datetime:
    return datetime.now(UTC)

