from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.pydantic_compat import PYDANTIC_V2, ConfigDict

RiskSourceBucket = Literal["TRADINGVIEW", "SIGMATRADER", "MANUAL"]
RiskProduct = Literal["CNC", "MIS"]


class UnifiedRiskGlobalRead(BaseModel):
    enabled: bool = True
    manual_override_enabled: bool = False
    baseline_equity_inr: float = Field(default=0.0, ge=0.0)
    updated_at: datetime | None = None

    if PYDANTIC_V2:
        model_config = ConfigDict(extra="forbid")


class UnifiedRiskGlobalUpdate(BaseModel):
    enabled: bool = True
    manual_override_enabled: bool = False
    baseline_equity_inr: float = Field(default=0.0, ge=0.0)

    if PYDANTIC_V2:
        model_config = ConfigDict(extra="forbid")

class RiskSourceOverrideRead(BaseModel):
    source_bucket: Literal["TRADINGVIEW", "SIGMATRADER"]
    product: RiskProduct

    allow_product: bool | None = None

    allow_short_selling: bool | None = None
    max_order_value_pct: float | None = None
    max_order_value_abs: float | None = None
    max_quantity_per_order: float | None = None

    capital_per_trade: float | None = None
    max_positions: int | None = None
    max_exposure_pct: float | None = None

    risk_per_trade_pct: float | None = None
    hard_risk_pct: float | None = None
    stop_loss_mandatory: bool | None = None
    stop_reference: str | None = None
    atr_period: int | None = None
    atr_mult_initial_stop: float | None = None
    fallback_stop_pct: float | None = None
    min_stop_distance_pct: float | None = None
    max_stop_distance_pct: float | None = None

    daily_loss_pct: float | None = None
    hard_daily_loss_pct: float | None = None
    max_consecutive_losses: int | None = None

    entry_cutoff_time: str | None = None
    force_squareoff_time: str | None = None
    max_trades_per_day: int | None = None
    max_trades_per_symbol_per_day: int | None = None
    min_bars_between_trades: int | None = None
    cooldown_after_loss_bars: int | None = None

    slippage_guard_bps: float | None = None
    gap_guard_pct: float | None = None
    order_type_policy: str | None = None

    updated_at: datetime | None = None

    if PYDANTIC_V2:
        model_config = ConfigDict(extra="forbid")


class RiskSourceOverrideUpsert(BaseModel):
    source_bucket: Literal["TRADINGVIEW", "SIGMATRADER"]
    product: RiskProduct

    allow_product: bool | None = None

    allow_short_selling: bool | None = None
    max_order_value_pct: float | None = None
    max_order_value_abs: float | None = None
    max_quantity_per_order: float | None = None

    capital_per_trade: float | None = None
    max_positions: int | None = None
    max_exposure_pct: float | None = None

    risk_per_trade_pct: float | None = None
    hard_risk_pct: float | None = None
    stop_loss_mandatory: bool | None = None
    stop_reference: str | None = None
    atr_period: int | None = None
    atr_mult_initial_stop: float | None = None
    fallback_stop_pct: float | None = None
    min_stop_distance_pct: float | None = None
    max_stop_distance_pct: float | None = None

    daily_loss_pct: float | None = None
    hard_daily_loss_pct: float | None = None
    max_consecutive_losses: int | None = None

    entry_cutoff_time: str | None = None
    force_squareoff_time: str | None = None
    max_trades_per_day: int | None = None
    max_trades_per_symbol_per_day: int | None = None
    min_bars_between_trades: int | None = None
    cooldown_after_loss_bars: int | None = None

    slippage_guard_bps: float | None = None
    gap_guard_pct: float | None = None
    order_type_policy: str | None = None

    if PYDANTIC_V2:
        model_config = ConfigDict(extra="forbid")


__all__ = [
    "RiskProduct",
    "RiskSourceBucket",
    "UnifiedRiskGlobalRead",
    "UnifiedRiskGlobalUpdate",
    "RiskSourceOverrideRead",
    "RiskSourceOverrideUpsert",
]
