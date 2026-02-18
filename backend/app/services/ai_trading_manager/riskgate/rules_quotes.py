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
) -> List[str]:
    # Quotes can come from broker snapshot cache (Phase 1 will fetch on-demand).
    quotes: Dict[str, tuple[float, datetime]] = {}
    for q in broker.quotes_cache:
        quotes[str(q.symbol).upper()] = (float(q.last_price), q.as_of_ts)

    reasons: List[str] = []
    for sym in [s.upper() for s in plan.intent.symbols]:
        q = quotes.get(sym)
        if q is None:
            reasons.append(f"QUOTE_MISSING:{sym}")
            continue
        last_price, as_of = q
        if policy.require_nonzero_quotes and last_price <= 0:
            reasons.append(f"QUOTE_NONPOSITIVE:{sym}")
        age_sec = int((eval_ts - as_of).total_seconds())
        if age_sec > int(policy.quote_max_age_sec):
            reasons.append(f"QUOTE_STALE:{sym}")
    return reasons

