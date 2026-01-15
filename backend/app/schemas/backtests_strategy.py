from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.backtests_portfolio import BrokerName, ChargesModel, ProductType

StrategyTimeframe = Literal["1m", "5m", "15m", "30m", "1h", "1d"]
StrategyDirection = Literal["LONG", "SHORT"]
StrategyReentryMode = Literal["TREND_PULLBACK"]
StrategyReentryTrigger = Literal["CLOSE_CROSSES_ABOVE_FAST_MA"]
StrategyReentryTrendFilter = Literal["CLOSE_ABOVE_SLOW_MA"]


class StrategyBacktestConfigIn(BaseModel):
    timeframe: StrategyTimeframe = "1d"
    start_date: date
    end_date: date

    entry_dsl: str = Field(min_length=1)
    exit_dsl: str = Field(min_length=1)

    # Trading constraints
    product: ProductType = "CNC"
    direction: StrategyDirection = "LONG"

    initial_cash: float = Field(default=100000.0, ge=0.0)
    position_size_pct: float = Field(default=100.0, ge=0.0, le=100.0)

    # Risk controls (optional; set to 0 to disable)
    stop_loss_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    take_profit_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    trailing_stop_pct: float = Field(default=0.0, ge=0.0, le=100.0)

    # Re-entry after trailing stop (feature-gated; Strategy tab only)
    allow_reentry_after_trailing_stop: bool = False
    reentry_mode: StrategyReentryMode = "TREND_PULLBACK"
    reentry_cooldown_bars: int = Field(default=1, ge=0, le=20)
    reentry_trigger: StrategyReentryTrigger = "CLOSE_CROSSES_ABOVE_FAST_MA"
    reentry_trend_filter: StrategyReentryTrendFilter = "CLOSE_ABOVE_SLOW_MA"
    # 0 = unlimited
    max_reentries_per_trend: int = Field(default=999, ge=0, le=9999)

    # Equity drawdown controls (optional; set to 0 to disable)
    # - global: from peak since start ("kill switch"; stops new entries)
    # - trade: from peak since last entry (equity trailing stop for the current trade)
    max_equity_dd_global_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    max_equity_dd_trade_pct: float = Field(default=0.0, ge=0.0, le=100.0)

    # Execution assumptions
    slippage_bps: float = Field(default=0.0, ge=0.0, le=2000.0)
    charges_model: ChargesModel = "BROKER"
    charges_bps: float = Field(default=0.0, ge=0.0, le=2000.0)
    charges_broker: BrokerName = "zerodha"
    include_dp_charges: bool = True


__all__ = [
    "StrategyBacktestConfigIn",
    "StrategyDirection",
    "StrategyReentryMode",
    "StrategyReentryTrendFilter",
    "StrategyReentryTrigger",
    "StrategyTimeframe",
]
