from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from app.schemas.ai_trading_manager import BrokerSnapshot, TradePlan

from .policy_config import RiskPolicyConfig


def evaluate_quote_rules(
    *,
    policy: RiskPolicyConfig,
    plan: TradePlan,
    broker: BrokerSnapshot,
    eval_ts: datetime,
) -> List[dict]:
    # Quotes can come from broker snapshot cache (Phase 1 will fetch on-demand).
    quotes: Dict[str, tuple[float, datetime]] = {}
    for q in broker.quotes_cache:
        quotes[str(q.symbol).upper()] = (float(q.last_price), q.as_of_ts)

    reasons: List[dict] = []
    for sym in [s.upper() for s in plan.intent.symbols]:
        q = quotes.get(sym)
        if q is None:
            reasons.append({"code": "QUOTE_MISSING", "message": "Quote missing.", "details": {"symbol": sym}})
            continue
        last_price, as_of = q
        if policy.require_nonzero_quotes and last_price <= 0:
            reasons.append(
                {
                    "code": "QUOTE_NONPOSITIVE",
                    "message": "Quote is non-positive.",
                    "details": {"symbol": sym, "last_price": last_price},
                }
            )
        age_sec = int((eval_ts - as_of).total_seconds())
        if age_sec > int(policy.quote_max_age_sec):
            reasons.append(
                {
                    "code": "QUOTE_STALE",
                    "message": "Quote is stale.",
                    "details": {"symbol": sym, "age_sec": age_sec},
                }
            )
    return reasons
