from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Set

from app.schemas.ai_settings import AiSettings

from .lsg_types import TelemetryTier, ToolCapability, ToolRequestSource


# Single policy map (code-based, consistent with existing ai_toolcalling/policy.py).
REMOTE_MARKET_DATA_TOOLS: Set[str] = {
    "search_instruments",
    "get_ltp",
    "get_quotes",
    "get_ohlc",
    "get_historical_data",
}

REMOTE_HARD_DENY_IDENTITY_AUTH: Set[str] = {
    "get_profile",
    "login",
}

REMOTE_HARD_DENY_TRADING_WRITE: Set[str] = {
    "place_order",
    "modify_order",
    "cancel_order",
    "place_gtt_order",
    "modify_gtt_order",
    "delete_gtt_order",
}

REMOTE_DENY_RAW_ACCOUNT_READS: Set[str] = {
    "get_holdings",
    "get_positions",
    "get_orders",
    "get_order_history",
    "get_order_trades",
    "get_trades",
    "get_margins",
    "get_mf_holdings",
}

TIER3_ALWAYS_BLOCK_KEYS: Set[str] = {
    # Identity/auth tools are always Tier-3.
    *REMOTE_HARD_DENY_IDENTITY_AUTH,
}

LOCAL_DIGEST_TOOLS: Set[str] = {
    "portfolio_digest",
    "orders_digest",
    "risk_digest",
}

INTERNAL_TRADING_INTENT_TOOLS: Set[str] = {
    "propose_trade_plan",
}

INTERNAL_TRADING_WRITE_TOOLS: Set[str] = {
    "execute_trade_plan",
}


def capability_for_tool(tool_name: str) -> ToolCapability:
    n = (tool_name or "").strip()
    if not n:
        return ToolCapability.TRADING_WRITE
    if n in REMOTE_MARKET_DATA_TOOLS:
        return ToolCapability.MARKET_DATA_READONLY
    if n in LOCAL_DIGEST_TOOLS:
        return ToolCapability.ACCOUNT_DIGEST
    if n in INTERNAL_TRADING_INTENT_TOOLS:
        return ToolCapability.TRADING_INTENT
    if n in INTERNAL_TRADING_WRITE_TOOLS or n in REMOTE_HARD_DENY_TRADING_WRITE:
        return ToolCapability.TRADING_WRITE
    if n in REMOTE_HARD_DENY_IDENTITY_AUTH:
        return ToolCapability.IDENTITY_AUTH
    if n in REMOTE_DENY_RAW_ACCOUNT_READS:
        return ToolCapability.ACCOUNT_READ
    # Unknown is treated as write-tier (fail closed).
    return ToolCapability.TRADING_WRITE


def telemetry_tier_for_tool(tool_name: str) -> TelemetryTier:
    n = (tool_name or "").strip()
    if not n:
        return TelemetryTier.TIER_3
    if n in REMOTE_MARKET_DATA_TOOLS:
        return TelemetryTier.TIER_1
    if n in LOCAL_DIGEST_TOOLS or n in REMOTE_DENY_RAW_ACCOUNT_READS:
        return TelemetryTier.TIER_2
    if n in REMOTE_HARD_DENY_IDENTITY_AUTH or n in REMOTE_HARD_DENY_TRADING_WRITE:
        return TelemetryTier.TIER_3
    # Unknown tools are treated as Tier-3 (fail closed).
    return TelemetryTier.TIER_3


@dataclass(frozen=True)
class LsgPolicyDecision:
    allowed: bool
    capability: ToolCapability
    telemetry_tier: TelemetryTier
    reason: str | None = None
    denial_reason: str = "policy"  # policy|capability|pii|rate_limit|invalid_args


def evaluate_lsg_policy(
    *,
    source: ToolRequestSource,
    tool_name: str,
    tm_cfg: AiSettings,
) -> LsgPolicyDecision:
    """Central, capability-based policy gate for the Local Security Gateway (LSG).

    Notes:
    - For backwards compatibility, non-remote sources are permissive here and rely
      on the legacy tool policy and safe summary enforcement in the orchestrator.
    - Remote restrictions are strict and config-driven via tm_cfg.hybrid_llm toggles.
    """
    cap = capability_for_tool(tool_name)
    tier = telemetry_tier_for_tool(tool_name)
    n = (tool_name or "").strip()

    if source != "remote":
        return LsgPolicyDecision(allowed=True, capability=cap, telemetry_tier=tier)

    # Remote: hard denies.
    if n in REMOTE_HARD_DENY_IDENTITY_AUTH:
        return LsgPolicyDecision(
            allowed=False,
            capability=ToolCapability.IDENTITY_AUTH,
            telemetry_tier=TelemetryTier.TIER_3,
            reason="Remote is hard-denied for identity/auth tools.",
            denial_reason="capability",
        )
    if n in REMOTE_HARD_DENY_TRADING_WRITE:
        return LsgPolicyDecision(
            allowed=False,
            capability=ToolCapability.TRADING_WRITE,
            telemetry_tier=TelemetryTier.TIER_3,
            reason="Remote is hard-denied for broker write tools.",
            denial_reason="capability",
        )

    # Tier-2: portfolio telemetry posture (explicit user setting).
    hy = getattr(tm_cfg, "hybrid_llm", None)
    detail_raw = getattr(hy, "remote_portfolio_detail_level", None)
    detail = str(getattr(detail_raw, "value", None) or detail_raw or "DIGEST_ONLY").upper()
    if n in REMOTE_DENY_RAW_ACCOUNT_READS:
        if detail != "FULL_SANITIZED":
            return LsgPolicyDecision(
                allowed=False,
                capability=ToolCapability.ACCOUNT_READ,
                telemetry_tier=TelemetryTier.TIER_2,
                reason="Remote portfolio detail level does not allow raw account reads; request a digest tool instead.",
                denial_reason="capability",
            )
        return LsgPolicyDecision(
            allowed=True,
            capability=ToolCapability.ACCOUNT_READ,
            telemetry_tier=TelemetryTier.TIER_2,
            reason="Allowed by FULL_SANITIZED remote portfolio detail level (sanitization enforced).",
            denial_reason="policy",
        )

    # Remote: conditional allows.
    if n in REMOTE_MARKET_DATA_TOOLS:
        if not bool(getattr(getattr(tm_cfg, "hybrid_llm", None), "allow_remote_market_data_tools", False)):
            return LsgPolicyDecision(
                allowed=False,
                capability=ToolCapability.MARKET_DATA_READONLY,
                telemetry_tier=TelemetryTier.TIER_1,
                reason="Remote market-data tools are disabled by settings.",
                denial_reason="policy",
            )
        return LsgPolicyDecision(allowed=True, capability=ToolCapability.MARKET_DATA_READONLY, telemetry_tier=TelemetryTier.TIER_1)

    if n in LOCAL_DIGEST_TOOLS:
        if detail == "OFF":
            return LsgPolicyDecision(
                allowed=False,
                capability=ToolCapability.ACCOUNT_DIGEST,
                telemetry_tier=TelemetryTier.TIER_2,
                reason="Remote portfolio detail level is OFF; portfolio telemetry is not exposed to remote.",
                denial_reason="policy",
            )
        if not bool(getattr(getattr(tm_cfg, "hybrid_llm", None), "allow_remote_account_digests", False)):
            return LsgPolicyDecision(
                allowed=False,
                capability=ToolCapability.ACCOUNT_DIGEST,
                telemetry_tier=TelemetryTier.TIER_2,
                reason="Remote digest tools are disabled by settings.",
                denial_reason="policy",
            )
        return LsgPolicyDecision(allowed=True, capability=ToolCapability.ACCOUNT_DIGEST, telemetry_tier=TelemetryTier.TIER_2)

    if n in INTERNAL_TRADING_INTENT_TOOLS or n in INTERNAL_TRADING_WRITE_TOOLS:
        # Internal ST tool surface is allowed to remote in hybrid mode; execution remains
        # gated by deterministic checks (explicit execute, kill switches, RiskGate).
        return LsgPolicyDecision(allowed=True, capability=cap, telemetry_tier=TelemetryTier.TIER_3)

    # Unknown tools: deny fail-closed.
    return LsgPolicyDecision(
        allowed=False,
        capability=cap,
        telemetry_tier=TelemetryTier.TIER_3,
        reason="Remote tool is not allowlisted.",
        denial_reason="policy",
    )


def lsg_policy_debug_map() -> Dict[str, Any]:
    """Expose the single policy map for debugging / audit."""
    return {
        "remote_market_data_tools": sorted(REMOTE_MARKET_DATA_TOOLS),
        "remote_hard_deny_identity_auth": sorted(REMOTE_HARD_DENY_IDENTITY_AUTH),
        "remote_hard_deny_trading_write": sorted(REMOTE_HARD_DENY_TRADING_WRITE),
        "remote_deny_raw_account_reads": sorted(REMOTE_DENY_RAW_ACCOUNT_READS),
        "local_digest_tools": sorted(LOCAL_DIGEST_TOOLS),
        "internal_trading_intent_tools": sorted(INTERNAL_TRADING_INTENT_TOOLS),
        "internal_trading_write_tools": sorted(INTERNAL_TRADING_WRITE_TOOLS),
    }


__all__ = [
    "INTERNAL_TRADING_INTENT_TOOLS",
    "INTERNAL_TRADING_WRITE_TOOLS",
    "LOCAL_DIGEST_TOOLS",
    "LsgPolicyDecision",
    "REMOTE_DENY_RAW_ACCOUNT_READS",
    "REMOTE_HARD_DENY_IDENTITY_AUTH",
    "REMOTE_HARD_DENY_TRADING_WRITE",
    "REMOTE_MARKET_DATA_TOOLS",
    "capability_for_tool",
    "evaluate_lsg_policy",
    "lsg_policy_debug_map",
]
