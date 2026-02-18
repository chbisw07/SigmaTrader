from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List

from app.schemas.ai_trading_manager import (
    BrokerSnapshot,
    LedgerSnapshot,
    RiskDecision,
    RiskDecisionOutcome,
    TradePlan,
)

from .policy_config import RiskPolicyConfig, default_policy
from .rules_core import evaluate_core_rules
from .rules_market import evaluate_market_hours
from .rules_quotes import evaluate_quote_rules


@dataclass(frozen=True)
class RiskGateResult:
    decision: RiskDecision
    computed_metrics: Dict[str, float]


def evaluate_riskgate(
    *,
    plan: TradePlan,
    broker: BrokerSnapshot,
    ledger: LedgerSnapshot,
    policy: RiskPolicyConfig | None = None,
    eval_ts: datetime | None = None,
) -> RiskGateResult:
    policy = policy or default_policy()
    policy_norm = policy.normalized()
    eval_ts = eval_ts or broker.as_of_ts

    reasons: List[str] = []
    reasons.extend(evaluate_market_hours(plan=plan, eval_ts=eval_ts))
    reasons.extend(evaluate_quote_rules(policy=policy_norm, plan=plan, broker=broker, eval_ts=eval_ts))
    reasons.extend(evaluate_core_rules(policy=policy_norm, plan=plan, broker=broker, ledger=ledger))

    computed_metrics: Dict[str, float] = {
        "open_positions": float(len(ledger.expected_positions)),
        "symbols_count": float(len(plan.intent.symbols)),
    }
    if plan.intent.risk_budget_pct is not None:
        computed_metrics["risk_budget_pct"] = float(plan.intent.risk_budget_pct)

    outcome = RiskDecisionOutcome.deny if reasons else RiskDecisionOutcome.allow
    decision = RiskDecision(
        outcome=outcome,
        reasons=reasons,
        computed_risk_metrics=computed_metrics,
        policy_version=policy_norm.version,
        policy_hash=policy_norm.content_hash(),
    )
    return RiskGateResult(decision=decision, computed_metrics=computed_metrics)

