from __future__ import annotations

from typing import List

from app.schemas.ai_trading_manager import BrokerSnapshot, LedgerSnapshot, TradePlan

from .policy_config import RiskPolicyConfig
from ..sizing import extract_equity_value


def evaluate_core_rules(
    *,
    policy: RiskPolicyConfig,
    plan: TradePlan,
    broker: BrokerSnapshot,
    ledger: LedgerSnapshot,
) -> List[dict]:
    reasons: List[dict] = []

    def _add(code: str, message: str, *, severity: str = "deny", **details) -> None:
        reasons.append({"code": code, "message": message, "severity": severity, "details": details})

    intent = plan.intent
    symbols = [s.upper() for s in intent.symbols]

    if len(symbols) > int(policy.max_symbols_per_plan):
        _add(
            "TOO_MANY_SYMBOLS",
            "Too many symbols in a single plan.",
            count=len(symbols),
            max=int(policy.max_symbols_per_plan),
        )

    product = str(intent.product or "").upper()
    if policy.allowed_products and product not in set(policy.normalized().allowed_products):
        _add("PRODUCT_NOT_ALLOWED", "Product is not allowed by policy.", product=product)

    order_type = str((plan.order_skeleton or {}).get("order_type") or "MARKET").upper()
    if policy.allowed_order_types and order_type not in set(policy.normalized().allowed_order_types):
        _add("ORDER_TYPE_NOT_ALLOWED", "Order type is not allowed by policy.", order_type=order_type)

    if policy.deny_symbols:
        denied = sorted(set(symbols) & set(policy.normalized().deny_symbols))
        if denied:
            _add("SYMBOL_DENY_LIST", "Symbol is denied by policy.", symbols=denied)

    if policy.allow_symbols:
        allow = set(policy.normalized().allow_symbols)
        not_allowed = sorted([s for s in symbols if s not in allow])
        if not_allowed:
            _add("SYMBOL_NOT_ALLOW_LISTED", "Symbol is not in allowlist.", symbols=not_allowed)

    if intent.risk_budget_pct is not None and float(intent.risk_budget_pct) > float(policy.max_per_trade_risk_pct):
        _add(
            "RISK_BUDGET_EXCEEDS_MAX",
            "Risk budget exceeds max per-trade risk percent.",
            risk_budget_pct=float(intent.risk_budget_pct),
            max_per_trade_risk_pct=float(policy.max_per_trade_risk_pct),
        )

    open_positions = len(ledger.expected_positions)
    if open_positions >= int(policy.max_open_positions):
        _add(
            "MAX_OPEN_POSITIONS_EXCEEDED",
            "Max open positions exceeded.",
            open_positions=open_positions,
            max_open_positions=int(policy.max_open_positions),
        )

    # Broker snapshot is canonical; if it's clearly stale, deny execution in Phase 0.
    if broker.as_of_ts < ledger.as_of_ts:
        # Not an automatic deny yet, but record as a reason so higher layers can decide.
        _add(
            "BROKER_SNAPSHOT_OLDER_THAN_LEDGER",
            "Broker snapshot is older than expected ledger.",
            severity="warn",
        )

    # Notional / exposure sanity checks (best-effort; requires quotes + equity extraction).
    equity = extract_equity_value(broker.margins or {})
    qty_raw = (intent.constraints or {}).get("qty")
    try:
        qty = float(qty_raw) if qty_raw is not None else None
    except Exception:
        qty = None
    quotes = {str(q.symbol).upper(): float(q.last_price) for q in (broker.quotes_cache or [])}
    if equity and qty and qty > 0 and quotes:
        planned_notional = 0.0
        for sym in symbols:
            px = quotes.get(sym)
            if px and px > 0:
                planned_notional += float(qty) * float(px)
        max_notional = float(equity) * (float(policy.max_per_trade_notional_pct) / 100.0)
        if planned_notional > max_notional:
            _add(
                "NOTIONAL_EXCEEDS_MAX",
                "Planned trade notional exceeds policy max.",
                planned_notional=planned_notional,
                max_notional=max_notional,
                equity=equity,
            )

        # Current exposure based on broker positions + cached quotes (best-effort).
        current_exposure = 0.0
        for p in broker.positions or []:
            sym = str(p.symbol).upper()
            px = quotes.get(sym)
            if px and px > 0:
                current_exposure += abs(float(p.qty)) * float(px)
        max_total = float(equity) * (float(policy.max_total_exposure_pct) / 100.0)
        if (current_exposure + planned_notional) > max_total:
            _add(
                "EXPOSURE_EXCEEDS_MAX_TOTAL",
                "Total exposure exceeds policy max.",
                current_exposure=current_exposure,
                planned_notional=planned_notional,
                max_total=max_total,
                equity=equity,
            )

    return reasons
