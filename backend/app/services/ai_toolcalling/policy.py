from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Set


SAFE_READ_TOOL_ALLOWLIST: Set[str] = {
    "get_holdings",
    "get_positions",
    "get_orders",
    "get_margins",
    "get_profile",
}


def _is_destructive(tool: dict[str, Any]) -> bool:
    ann = tool.get("annotations")
    if isinstance(ann, dict) and ann.get("destructiveHint") is True:
        return True
    name = str(tool.get("name") or "").lower()
    # Very defensive fallback.
    if any(k in name for k in ("place_", "cancel_", "modify_", "exit_", "squareoff", "sell_", "buy_")):
        return True
    return False


@dataclass(frozen=True)
class ToolPolicyDecision:
    allowed: bool
    reason: str | None = None
    category: str = "read"


def classify_tool(tool_name: str, tool_meta: dict[str, Any] | None = None) -> str:
    n = (tool_name or "").strip().lower()
    if n in SAFE_READ_TOOL_ALLOWLIST:
        return "read"
    if tool_meta and _is_destructive(tool_meta):
        return "trade"
    # Unknown tools are treated as dangerous by default.
    return "blocked"


def evaluate_tool_policy(
    *,
    tool_name: str,
    tool_meta: dict[str, Any] | None,
    user_message: str,
    ai_execution_enabled: bool,
) -> ToolPolicyDecision:
    category = classify_tool(tool_name, tool_meta)
    if category == "read":
        return ToolPolicyDecision(allowed=True, category="read")

    # MVP: block all trade/unknown tools unless we later wire RiskGate + execution.
    if category == "trade":
        if not ai_execution_enabled:
            return ToolPolicyDecision(
                allowed=False,
                category="trade",
                reason="Trade/execution tools are disabled (enable AI execution first).",
            )
        return ToolPolicyDecision(
            allowed=False,
            category="trade",
            reason="Trade/execution via MCP is not enabled in this MVP; policy veto is mandatory.",
        )

    return ToolPolicyDecision(
        allowed=False,
        category="blocked",
        reason="This tool is not allowlisted. Only read-only portfolio tools are permitted in the MVP.",
    )


def tool_lookup_map(tools_list: Iterable[dict[str, Any]]) -> Dict[str, dict[str, Any]]:
    out: Dict[str, dict[str, Any]] = {}
    for t in tools_list:
        if not isinstance(t, dict):
            continue
        name = str(t.get("name") or "").strip()
        if not name:
            continue
        out[name] = t
    return out


__all__ = [
    "SAFE_READ_TOOL_ALLOWLIST",
    "ToolPolicyDecision",
    "classify_tool",
    "evaluate_tool_policy",
    "tool_lookup_map",
]
