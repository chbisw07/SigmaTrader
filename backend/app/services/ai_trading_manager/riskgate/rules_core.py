from __future__ import annotations

from typing import List

from app.schemas.ai_trading_manager import BrokerSnapshot, LedgerSnapshot, TradePlan

from .policy_config import RiskPolicyConfig


def evaluate_core_rules(
    *,
    policy: RiskPolicyConfig,
    plan: TradePlan,
    broker: BrokerSnapshot,
    ledger: LedgerSnapshot,
) -> List[str]:
    reasons: List[str] = []

    intent = plan.intent
    symbols = [s.upper() for s in intent.symbols]

    if policy.deny_symbols:
        denied = sorted(set(symbols) & set(policy.normalized().deny_symbols))
        if denied:
            reasons.append(f"SYMBOL_DENY_LIST:{','.join(denied)}")

    if policy.allow_symbols:
        allow = set(policy.normalized().allow_symbols)
        not_allowed = sorted([s for s in symbols if s not in allow])
        if not_allowed:
            reasons.append(f"SYMBOL_NOT_ALLOW_LISTED:{','.join(not_allowed)}")

    if intent.risk_budget_pct is not None and float(intent.risk_budget_pct) > float(policy.max_per_trade_risk_pct):
        reasons.append("RISK_BUDGET_EXCEEDS_MAX")

    open_positions = len(ledger.expected_positions)
    if open_positions >= int(policy.max_open_positions):
        reasons.append("MAX_OPEN_POSITIONS_EXCEEDED")

    # Broker snapshot is canonical; if it's clearly stale, deny execution in Phase 0.
    if broker.as_of_ts < ledger.as_of_ts:
        # Not an automatic deny yet, but record as a reason so higher layers can decide.
        reasons.append("BROKER_SNAPSHOT_OLDER_THAN_LEDGER")

    return reasons

