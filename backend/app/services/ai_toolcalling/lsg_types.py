from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ToolCapability(str, Enum):
    MARKET_DATA_READONLY = "MARKET_DATA_READONLY"
    ACCOUNT_READ = "ACCOUNT_READ"
    ACCOUNT_DIGEST = "ACCOUNT_DIGEST"
    TRADING_INTENT = "TRADING_INTENT"
    TRADING_WRITE = "TRADING_WRITE"
    IDENTITY_AUTH = "IDENTITY_AUTH"

class TelemetryTier(str, Enum):
    """Exposure classification for remote models.

    Tier-1: public market data (safe to share to remote).
    Tier-2: portfolio telemetry (user-controlled).
    Tier-3: PII/secrets/session artifacts (always blocked).
    """

    TIER_1 = "TIER_1"
    TIER_2 = "TIER_2"
    TIER_3 = "TIER_3"


ToolRequestSource = Literal["remote", "local", "system", "legacy_llm"]


class ToolRequestEnvelope(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    source: ToolRequestSource
    mode: str = Field(min_length=1, max_length=32)
    capability: ToolCapability
    tool_name: str = Field(min_length=1, max_length=128)
    args: Dict[str, Any] = Field(default_factory=dict)
    reason: Optional[str] = Field(default=None, max_length=2000)
    risk_tier: Optional[str] = Field(default=None, max_length=64)


ToolResultStatus = Literal["ok", "denied", "error"]
ToolDenialReason = Literal["policy", "capability", "pii", "rate_limit", "invalid_args"]


class ToolSanitizationMeta(BaseModel):
    redacted_fields: List[str] = Field(default_factory=list)
    bucketed_fields: List[str] = Field(default_factory=list)
    hashed_fields: List[str] = Field(default_factory=list)


class ToolResultEnvelope(BaseModel):
    request_id: str
    status: ToolResultStatus
    denial_reason: Optional[ToolDenialReason] = None
    data: Any = None
    sanitization: ToolSanitizationMeta = Field(default_factory=ToolSanitizationMeta)
    audit_ref: Optional[str] = None


__all__ = [
    "TelemetryTier",
    "ToolCapability",
    "ToolDenialReason",
    "ToolRequestEnvelope",
    "ToolRequestSource",
    "ToolResultEnvelope",
    "ToolResultStatus",
    "ToolSanitizationMeta",
]
