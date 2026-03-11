from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Tuple


class TrustTier(str, Enum):
    local_model = "LOCAL_MODEL"
    remote_model = "REMOTE_MODEL"


ApprovalKind = Literal["remote_portfolio_detail", "tavily_over_limit"]


@dataclass(frozen=True)
class ApprovalOption:
    id: str
    label: str
    grant: int | None = None


@dataclass(frozen=True)
class ApprovalRequest:
    kind: ApprovalKind
    title: str
    message: str
    options: List[ApprovalOption]
    meta: Dict[str, Any]


class ApprovalRequired(RuntimeError):
    def __init__(self, approval: ApprovalRequest):
        super().__init__(approval.message)
        self.approval = approval


def tavily_budget_decision(
    *,
    state: Dict[str, Any],
    warning_threshold: int,
    max_calls_per_session: int,
) -> Tuple[str, Dict[str, Any]]:
    """Return (decision, meta) for Tavily call.

    Decision:
      - "allow"
      - "warn"
      - "approval_required"
    """
    calls = int(state.get("tavily_calls_session") or 0)
    extra = int(state.get("tavily_extra_calls_allowed") or 0)
    warn_at = int(warning_threshold or 0)
    max_calls = int(max_calls_per_session or 0)

    # Fail-closed defaults.
    if max_calls <= 0:
        return "approval_required", {"calls": calls, "extra": extra, "max_calls": max_calls, "warn_at": warn_at}

    if calls < max_calls:
        if warn_at and calls + 1 >= warn_at:
            return "warn", {"calls": calls, "extra": extra, "max_calls": max_calls, "warn_at": warn_at}
        return "allow", {"calls": calls, "extra": extra, "max_calls": max_calls, "warn_at": warn_at}

    # calls >= max_calls: require extra allowance.
    if extra > 0:
        return "warn" if (warn_at and calls + 1 >= warn_at) else "allow", {
            "calls": calls,
            "extra": extra,
            "max_calls": max_calls,
            "warn_at": warn_at,
        }
    return "approval_required", {"calls": calls, "extra": extra, "max_calls": max_calls, "warn_at": warn_at}


def portfolio_detail_requires_approval(*, state: Dict[str, Any]) -> bool:
    if bool(state.get("portfolio_access_session")):
        return False
    return not bool(state.get("portfolio_access_approved"))

