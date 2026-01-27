from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


RiskProduct = Literal["CNC", "MIS"]
RiskCategory = Literal["LC", "MC", "SC", "ETF"]
DrawdownState = Literal["NORMAL", "CAUTION", "DEFENSE", "HALT"]


RiskEngineV2FlagSource = Literal["db", "env_default", "db_invalid"]


class RiskEngineV2FlagRead(BaseModel):
    enabled: bool
    source: RiskEngineV2FlagSource
    updated_at: datetime | None = None


class RiskEngineV2FlagUpdate(BaseModel):
    enabled: bool


class RiskProfileBase(BaseModel):
    name: str
    product: RiskProduct

    capital_per_trade: float = 0.0
    max_positions: int = 0
    max_exposure_pct: float = 0.0

    risk_per_trade_pct: float = 0.0
    hard_risk_pct: float = 0.0

    daily_loss_pct: float = 0.0
    hard_daily_loss_pct: float = 0.0
    max_consecutive_losses: int = 0

    drawdown_mode: Literal["SETTINGS_BY_CATEGORY"] = "SETTINGS_BY_CATEGORY"

    force_exit_time: str | None = None

    entry_cutoff_time: str | None = None
    force_squareoff_time: str | None = None
    max_trades_per_day: int | None = None
    max_trades_per_symbol_per_day: int | None = None
    min_bars_between_trades: int | None = None
    cooldown_after_loss_bars: int | None = None
    slippage_guard_bps: float | None = None
    gap_guard_pct: float | None = None
    order_type_policy: str | None = None
    leverage_mode: str | None = None
    max_effective_leverage: float | None = None
    max_margin_used_pct: float | None = None

    enabled: bool = True
    is_default: bool = False


class RiskProfileCreate(RiskProfileBase):
    pass


class RiskProfileUpdate(BaseModel):
    name: Optional[str] = None
    product: Optional[RiskProduct] = None

    capital_per_trade: Optional[float] = None
    max_positions: Optional[int] = None
    max_exposure_pct: Optional[float] = None

    risk_per_trade_pct: Optional[float] = None
    hard_risk_pct: Optional[float] = None

    daily_loss_pct: Optional[float] = None
    hard_daily_loss_pct: Optional[float] = None
    max_consecutive_losses: Optional[int] = None

    drawdown_mode: Optional[Literal["SETTINGS_BY_CATEGORY"]] = None

    force_exit_time: Optional[str | None] = None

    entry_cutoff_time: Optional[str | None] = None
    force_squareoff_time: Optional[str | None] = None
    max_trades_per_day: Optional[int | None] = None
    max_trades_per_symbol_per_day: Optional[int | None] = None
    min_bars_between_trades: Optional[int | None] = None
    cooldown_after_loss_bars: Optional[int | None] = None
    slippage_guard_bps: Optional[float | None] = None
    gap_guard_pct: Optional[float | None] = None
    order_type_policy: Optional[str | None] = None
    leverage_mode: Optional[str | None] = None
    max_effective_leverage: Optional[float | None] = None
    max_margin_used_pct: Optional[float | None] = None

    enabled: Optional[bool] = None
    is_default: Optional[bool] = None


class RiskProfileRead(RiskProfileBase):
    id: int
    created_at: datetime
    updated_at: datetime


class SymbolRiskCategoryUpsert(BaseModel):
    broker_name: str = "zerodha"
    symbol: str
    exchange: str = "NSE"
    risk_category: RiskCategory


class SymbolRiskCategoryRead(SymbolRiskCategoryUpsert):
    id: int
    user_id: int | None
    created_at: datetime
    updated_at: datetime


class DrawdownThresholdUpsert(BaseModel):
    product: RiskProduct
    category: RiskCategory
    caution_pct: float = Field(ge=0)
    defense_pct: float = Field(ge=0)
    hard_stop_pct: float = Field(ge=0)


class DrawdownThresholdRead(DrawdownThresholdUpsert):
    id: int
    user_id: int | None
    created_at: datetime
    updated_at: datetime


class EquitySnapshotRead(BaseModel):
    id: int
    user_id: int | None
    as_of_date: date
    equity: float
    peak_equity: float
    drawdown_pct: float
    created_at: datetime
    updated_at: datetime


class AlertDecisionLogRead(BaseModel):
    id: int
    created_at: datetime
    user_id: int | None
    alert_id: int | None
    order_id: int | None

    source: str
    strategy_ref: str | None
    symbol: str | None
    exchange: str | None
    side: str | None
    trigger_price: float | None

    product_hint: str | None
    resolved_product: str | None
    risk_profile_id: int | None
    risk_category: str | None
    drawdown_pct: float | None
    drawdown_state: str | None

    decision: str
    reasons_json: str = "[]"
    details_json: str = "{}"


__all__ = [
    "AlertDecisionLogRead",
    "DrawdownState",
    "DrawdownThresholdRead",
    "DrawdownThresholdUpsert",
    "EquitySnapshotRead",
    "RiskEngineV2FlagRead",
    "RiskEngineV2FlagUpdate",
    "RiskCategory",
    "RiskProduct",
    "RiskProfileCreate",
    "RiskProfileRead",
    "RiskProfileUpdate",
    "SymbolRiskCategoryRead",
    "SymbolRiskCategoryUpsert",
]
