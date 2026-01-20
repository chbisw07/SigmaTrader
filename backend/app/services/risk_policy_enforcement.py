from __future__ import annotations

from typing import Literal

from app.schemas.risk_policy import RiskPolicy

RiskPolicyGroup = Literal[
    "account_level",
    "per_trade",
    "position_sizing",
    "stop_rules",
    "trade_frequency",
    "loss_controls",
    "correlation_controls",
    "execution_safety",
    "emergency_controls",
    "overrides",
]


def is_group_enforced(policy: RiskPolicy, group: RiskPolicyGroup) -> bool:
    """Return True when the global policy and the given group are enforced."""

    if not bool(getattr(policy, "enabled", False)):
        return False
    enforcement = getattr(policy, "enforcement", None)
    if enforcement is None:
        return True
    return bool(getattr(enforcement, group, True))


__all__ = ["RiskPolicyGroup", "is_group_enforced"]

