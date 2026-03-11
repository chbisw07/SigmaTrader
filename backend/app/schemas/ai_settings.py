from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class KiteMcpStatus(str, Enum):
    connected = "connected"
    disconnected = "disconnected"
    error = "error"
    unknown = "unknown"


class AiFeatureFlags(BaseModel):
    ai_assistant_enabled: bool = False
    ai_execution_enabled: bool = False
    kite_mcp_enabled: bool = False
    monitoring_enabled: bool = False


class AiKillSwitch(BaseModel):
    ai_execution_kill_switch: bool = False
    execution_disabled_until_ts: Optional[datetime] = None


class KiteMcpScopes(BaseModel):
    read_only: bool = True
    trade: bool = False


class KiteMcpConfig(BaseModel):
    server_url: Optional[str] = None
    transport_mode: str = "remote"  # local|remote (best-effort; not enforced yet)
    auth_method: str = "none"  # none|token|oauth|totp (profile only; no flow yet)
    auth_profile_ref: Optional[str] = None
    scopes: KiteMcpScopes = Field(default_factory=KiteMcpScopes)
    # Placeholder adapter selection until real MCP transport is implemented.
    broker_adapter: str = "zerodha"  # zerodha|angelone

    last_status: KiteMcpStatus = KiteMcpStatus.unknown
    last_checked_ts: Optional[datetime] = None
    last_connected_ts: Optional[datetime] = None
    tools_available_count: Optional[int] = None
    last_error: Optional[str] = None
    capabilities_cache: Dict[str, Any] = Field(default_factory=dict)


class LlmProvider(str, Enum):
    stub = "stub"
    openai = "openai"
    anthropic = "anthropic"
    local = "local"


class LlmLimits(BaseModel):
    max_tokens_per_request: Optional[int] = Field(default=None, ge=1)
    max_cost_usd_per_request: Optional[float] = Field(default=None, ge=0)
    max_cost_usd_per_day: Optional[float] = Field(default=None, ge=0)


class LlmProviderConfig(BaseModel):
    enabled: bool = False
    provider: LlmProvider = LlmProvider.stub
    model: Optional[str] = None
    do_not_send_pii: bool = True
    limits: LlmLimits = Field(default_factory=LlmLimits)


class AiSettings(BaseModel):
    feature_flags: AiFeatureFlags = Field(default_factory=AiFeatureFlags)
    kill_switch: AiKillSwitch = Field(default_factory=AiKillSwitch)
    kite_mcp: KiteMcpConfig = Field(default_factory=KiteMcpConfig)
    llm_provider: LlmProviderConfig = Field(default_factory=LlmProviderConfig)
    # Hybrid LLM (Local Security Gateway + Remote Reasoner). Default disabled for
    # backwards compatibility with the legacy OpenAI tool-calling loop.
    hybrid_llm: "HybridLlmConfig" = Field(default_factory=lambda: HybridLlmConfig())
    tool_guardrails: "ToolGuardrailsConfig" = Field(default_factory=lambda: ToolGuardrailsConfig())


class AiFeatureFlagsUpdate(BaseModel):
    ai_assistant_enabled: Optional[bool] = None
    ai_execution_enabled: Optional[bool] = None
    kite_mcp_enabled: Optional[bool] = None
    monitoring_enabled: Optional[bool] = None


class AiKillSwitchUpdate(BaseModel):
    ai_execution_kill_switch: Optional[bool] = None
    execution_disabled_until_ts: Optional[datetime] = None


class KiteMcpScopesUpdate(BaseModel):
    read_only: Optional[bool] = None
    trade: Optional[bool] = None


class KiteMcpConfigUpdate(BaseModel):
    server_url: Optional[str] = None
    transport_mode: Optional[str] = None
    auth_method: Optional[str] = None
    auth_profile_ref: Optional[str] = None
    scopes: Optional[KiteMcpScopesUpdate] = None
    broker_adapter: Optional[str] = None


class LlmLimitsUpdate(BaseModel):
    max_tokens_per_request: Optional[int] = Field(default=None, ge=1)
    max_cost_usd_per_request: Optional[float] = Field(default=None, ge=0)
    max_cost_usd_per_day: Optional[float] = Field(default=None, ge=0)


class LlmProviderConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    provider: Optional[LlmProvider] = None
    model: Optional[str] = None
    do_not_send_pii: Optional[bool] = None
    limits: Optional[LlmLimitsUpdate] = None


class AiSettingsUpdate(BaseModel):
    feature_flags: Optional[AiFeatureFlagsUpdate] = None
    kill_switch: Optional[AiKillSwitchUpdate] = None
    kite_mcp: Optional[KiteMcpConfigUpdate] = None
    llm_provider: Optional[LlmProviderConfigUpdate] = None
    hybrid_llm: Optional["HybridLlmConfigUpdate"] = None
    tool_guardrails: Optional["ToolGuardrailsConfigUpdate"] = None


class HybridLlmMode(str, Enum):
    auto = "AUTO"
    local_only = "LOCAL_ONLY"
    remote_only = "REMOTE_ONLY"
    hybrid = "HYBRID"

class RemotePortfolioDetailLevel(str, Enum):
    off = "OFF"
    digest_only = "DIGEST_ONLY"
    full_sanitized = "FULL_SANITIZED"


class HybridLlmConfig(BaseModel):
    enabled: bool = False
    # AUTO: if both remote + local provider configs exist, run HYBRID; else pick
    # the only available mode.
    mode: HybridLlmMode = HybridLlmMode.auto
    # Guardrails: remote is untrusted, so these are explicit toggles.
    allow_remote_market_data_tools: bool = False
    allow_remote_account_digests: bool = False
    # Tier-2 posture: what portfolio telemetry may be exposed to a remote model.
    # Default DIGEST_ONLY preserves the previous behavior where remote could
    # only see local digests (never raw holdings/orders payloads).
    remote_portfolio_detail_level: RemotePortfolioDetailLevel = RemotePortfolioDetailLevel.digest_only

    # Lightweight rate-limits (best-effort). Keys are tool names.
    # Example:
    # {"get_ltp": {"per_minute": 60, "per_symbol_per_minute": 30}}
    rate_limits: Dict[str, Any] = Field(default_factory=dict)


class HybridLlmConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    mode: Optional[HybridLlmMode] = None
    allow_remote_market_data_tools: Optional[bool] = None
    allow_remote_account_digests: Optional[bool] = None
    remote_portfolio_detail_level: Optional[RemotePortfolioDetailLevel] = None
    rate_limits: Optional[Dict[str, Any]] = None


class ToolGuardrailsConfig(BaseModel):
    # External tool guardrails (session-scoped).
    tavily_max_calls_per_session: int = Field(default=10, ge=0, le=10_000)
    tavily_warning_threshold: int = Field(default=8, ge=0, le=10_000)


class ToolGuardrailsConfigUpdate(BaseModel):
    tavily_max_calls_per_session: Optional[int] = Field(default=None, ge=0, le=10_000)
    tavily_warning_threshold: Optional[int] = Field(default=None, ge=0, le=10_000)


class KiteMcpTestRequest(BaseModel):
    server_url: Optional[str] = None
    fetch_capabilities: bool = True


class KiteMcpTestResponse(BaseModel):
    status: KiteMcpStatus
    checked_ts: datetime
    error: Optional[str] = None
    capabilities: Dict[str, Any] = Field(default_factory=dict)


class AiAuditResponse(BaseModel):
    items: List[Dict[str, Any]]
    next_offset: int
