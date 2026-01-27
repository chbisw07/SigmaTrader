from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

OrderSourceBucket = Literal["TRADINGVIEW", "SIGMATRADER"]
RiskProduct = Literal["CNC", "MIS"]
RiskCategory = Literal["LC", "MC", "SC", "ETF"]
DrawdownState = Literal["NORMAL", "CAUTION", "DEFENSE", "HARD_STOP"]


class CompiledRiskContext(BaseModel):
    product: RiskProduct
    category: RiskCategory
    scenario: DrawdownState | None = None
    symbol: str | None = None
    strategy_id: str | None = None


class CompiledDrawdownThresholds(BaseModel):
    caution_pct: float = 0.0
    defense_pct: float = 0.0
    hard_stop_pct: float = 0.0


class CompiledRiskProfileRef(BaseModel):
    id: int
    name: str
    product: RiskProduct
    enabled: bool
    is_default: bool


class CompiledRiskProvenance(BaseModel):
    source: Literal[
        "risk_policy",
        "profile",
        "drawdown_settings",
        "state_override",
        "computed",
        "default",
        "unknown",
    ]
    detail: str | None = None


class CompiledRiskOverride(BaseModel):
    field: str
    from_value: Any | None = None
    to_value: Any | None = None
    reason: str
    source: str


class CompiledRiskPolicyEffective(BaseModel):
    # Product gating
    allow_product: bool
    allow_short_selling: bool

    # Account-level caps (global)
    manual_equity_inr: float
    max_daily_loss_pct: float
    max_daily_loss_abs: float | None
    max_exposure_pct: float
    max_open_positions: int
    max_concurrent_symbols: int

    # Execution-layer caps (per order)
    max_order_value_pct: float
    max_order_value_abs_from_pct: float | None
    max_order_value_abs_override: float | None
    max_quantity_per_order: float | None

    # Per-trade risk
    max_risk_per_trade_pct: float
    hard_max_risk_pct: float
    stop_loss_mandatory: bool

    # Sizing
    capital_per_trade: float
    allow_scale_in: bool
    pyramiding: int

    # Stops model
    stop_reference: str
    atr_period: int
    atr_mult_initial_stop: float
    fallback_stop_pct: float
    min_stop_distance_pct: float
    max_stop_distance_pct: float
    trailing_stop_enabled: bool
    trail_activation_atr: float
    trail_activation_pct: float

    # Trade frequency + loss controls
    max_trades_per_symbol_per_day: int
    min_bars_between_trades: int
    cooldown_after_loss_bars: int
    max_consecutive_losses: int
    pause_after_loss_streak: bool
    pause_duration: str


class CompiledRiskV2Effective(BaseModel):
    # Drawdown + gating
    drawdown_pct: float | None
    drawdown_state: DrawdownState | None
    allow_new_entries: bool
    throttle_multiplier: float = 1.0

    # Profile selection
    profile: CompiledRiskProfileRef | None = None
    thresholds: CompiledDrawdownThresholds | None = None

    # Product-specific caps (from profile; throttles applied where relevant)
    capital_per_trade: float | None = None
    max_positions: int | None = None
    max_exposure_pct: float | None = None

    # Per-trade / daily controls (from profile)
    risk_per_trade_pct: float | None = None
    hard_risk_pct: float | None = None
    daily_loss_pct: float | None = None
    hard_daily_loss_pct: float | None = None
    max_consecutive_losses: int | None = None

    # MIS-only extensions
    entry_cutoff_time: str | None = None
    force_squareoff_time: str | None = None
    max_trades_per_day: int | None = None
    max_trades_per_symbol_per_day: int | None = None
    min_bars_between_trades: int | None = None
    cooldown_after_loss_bars: int | None = None
    slippage_guard_bps: float | None = None
    gap_guard_pct: float | None = None


class CompiledRiskInputs(BaseModel):
    compiled_at: datetime

    risk_policy_source: str
    risk_policy_enabled: bool
    risk_engine_v2_enabled: bool

    manual_equity_inr: float
    drawdown_pct: float | None = None


class CompiledRiskEffective(BaseModel):
    # Shared gating summary
    allow_new_entries: bool
    blocking_reasons: list[str] = Field(default_factory=list)

    # Risk Policy: values actually used by the legacy execution checks.
    risk_policy_by_source: dict[OrderSourceBucket, CompiledRiskPolicyEffective]

    # Product-specific risk engine (v2): profile + drawdown throttles.
    risk_engine_v2: CompiledRiskV2Effective


class CompiledRiskResponse(BaseModel):
    context: CompiledRiskContext
    inputs: CompiledRiskInputs
    effective: CompiledRiskEffective
    overrides: list[CompiledRiskOverride] = Field(default_factory=list)
    provenance: dict[str, CompiledRiskProvenance] = Field(default_factory=dict)


__all__ = [
    "CompiledRiskContext",
    "CompiledRiskResponse",
    "DrawdownState",
    "OrderSourceBucket",
    "RiskCategory",
    "RiskProduct",
]

