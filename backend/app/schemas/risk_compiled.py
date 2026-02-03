from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

RiskSourceBucket = Literal["TRADINGVIEW", "SIGMATRADER", "MANUAL"]
RiskProduct = Literal["CNC", "MIS"]
RiskCategory = Literal["LC", "MC", "SC", "ETF"]
DrawdownState = Literal["NORMAL", "CAUTION", "DEFENSE", "HARD_STOP"]


class CompiledRiskContext(BaseModel):
    product: RiskProduct
    category: RiskCategory
    source_bucket: RiskSourceBucket
    order_type: str | None = None
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
    source: Literal["global", "profile", "source_override", "computed", "default", "unknown"]
    detail: str | None = None


class CompiledRiskOverride(BaseModel):
    field: str
    from_value: Any | None = None
    to_value: Any | None = None
    reason: str
    source: str


class CompiledRiskInputs(BaseModel):
    compiled_at: datetime

    risk_enabled: bool
    manual_override_enabled: bool

    baseline_equity_inr: float
    drawdown_pct: float | None = None


class CompiledRiskEffective(BaseModel):
    allow_new_entries: bool
    blocking_reasons: list[str] = Field(default_factory=list)

    drawdown_state: DrawdownState | None = None
    throttle_multiplier: float = 1.0

    profile: CompiledRiskProfileRef | None = None
    thresholds: CompiledDrawdownThresholds | None = None

    # Source gating + per-order caps
    allow_product: bool = True
    allow_short_selling: bool = True
    max_order_value_pct: float | None = None
    max_order_value_abs: float | None = None
    max_quantity_per_order: float | None = None
    order_type_policy: str | None = None
    slippage_guard_bps: float | None = None
    gap_guard_pct: float | None = None

    # Profile / overrides (resolved)
    capital_per_trade: float | None = None
    max_positions: int | None = None
    max_exposure_pct: float | None = None

    daily_loss_pct: float | None = None
    hard_daily_loss_pct: float | None = None
    max_consecutive_losses: int | None = None

    risk_per_trade_pct: float | None = None
    hard_risk_pct: float | None = None

    # Stop-distance settings (resolved)
    stop_loss_mandatory: bool | None = None
    stop_reference: str | None = None
    atr_period: int | None = None
    atr_mult_initial_stop: float | None = None
    fallback_stop_pct: float | None = None
    min_stop_distance_pct: float | None = None
    max_stop_distance_pct: float | None = None

    # Trade frequency + time controls (resolved)
    entry_cutoff_time: str | None = None
    force_squareoff_time: str | None = None
    max_trades_per_day: int | None = None
    max_trades_per_symbol_per_day: int | None = None
    min_bars_between_trades: int | None = None
    cooldown_after_loss_bars: int | None = None


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
    "RiskCategory",
    "RiskProduct",
    "RiskSourceBucket",
]

