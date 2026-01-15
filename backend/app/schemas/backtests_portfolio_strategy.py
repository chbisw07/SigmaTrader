from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.backtests_portfolio import BrokerName, ChargesModel, ProductType
from app.schemas.backtests_strategy import StrategyDirection, StrategyTimeframe

PortfolioStrategyAllocationMode = Literal["EQUAL", "RANKING"]
PortfolioStrategyRankingMetric = Literal["PERF_PCT"]
PortfolioStrategySizingMode = Literal["PCT_EQUITY", "FIXED_CASH", "CASH_PER_SLOT"]
PortfolioStrategyReentryMode = Literal["TREND_PULLBACK"]
PortfolioStrategyReentryReplacePolicy = Literal[
    "REQUIRE_FREE_SLOT",
    "REQUIRE_FREE_SLOT_OR_REPLACE_WORST",
]
PortfolioStrategyReentryTrendFilter = Literal["NONE", "CLOSE_ABOVE_SLOW_MA"]
PortfolioStrategyReentryTrigger = Literal["CLOSE_CROSSES_ABOVE_FAST_MA"]


class PortfolioStrategyBacktestConfigIn(BaseModel):
    timeframe: StrategyTimeframe = "1d"
    start_date: date
    end_date: date

    entry_dsl: str = Field(min_length=1)
    exit_dsl: str = Field(min_length=1)

    product: ProductType = "CNC"
    direction: StrategyDirection = "LONG"

    initial_cash: float = Field(default=100000.0, ge=0.0)

    max_open_positions: int = Field(default=10, ge=1, le=200)

    allocation_mode: PortfolioStrategyAllocationMode = "EQUAL"
    ranking_metric: PortfolioStrategyRankingMetric = "PERF_PCT"
    ranking_window: int = Field(default=5, ge=1, le=400)

    sizing_mode: PortfolioStrategySizingMode = "PCT_EQUITY"
    position_size_pct: float = Field(default=20.0, ge=0.0, le=100.0)
    fixed_cash_per_trade: float = Field(default=0.0, ge=0.0)

    # Advanced constraints (optional; set to 0 to disable)
    min_holding_bars: int = Field(default=0, ge=0, le=10000)
    cooldown_bars: int = Field(default=0, ge=0, le=10000)
    max_symbol_alloc_pct: float = Field(default=0.0, ge=0.0, le=100.0)

    # Risk controls (optional; set to 0 to disable)
    stop_loss_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    take_profit_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    trailing_stop_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    max_equity_dd_global_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    max_equity_dd_trade_pct: float = Field(default=0.0, ge=0.0, le=100.0)

    # Re-entry after trailing stop (portfolio-aware; feature-gated)
    allow_reentry_after_trailing_stop: bool = False
    reentry_mode: PortfolioStrategyReentryMode = "TREND_PULLBACK"
    reentry_cooldown_bars: int = Field(default=3, ge=0, le=50)
    # 0 = unlimited
    reentry_max_per_symbol_per_trend: int = Field(default=1, ge=0, le=9999)
    reentry_rank_gate_enabled: bool = True
    reentry_rank_gate_buffer: int = Field(default=2, ge=0, le=50)
    reentry_replace_policy: PortfolioStrategyReentryReplacePolicy = (
        "REQUIRE_FREE_SLOT_OR_REPLACE_WORST"
    )
    reentry_trend_filter: PortfolioStrategyReentryTrendFilter = "CLOSE_ABOVE_SLOW_MA"
    reentry_trigger: PortfolioStrategyReentryTrigger = "CLOSE_CROSSES_ABOVE_FAST_MA"

    slippage_bps: float = Field(default=0.0, ge=0.0, le=2000.0)
    charges_model: ChargesModel = "BROKER"
    charges_bps: float = Field(default=0.0, ge=0.0, le=2000.0)
    charges_broker: BrokerName = "zerodha"
    include_dp_charges: bool = True


__all__ = [
    "PortfolioStrategyAllocationMode",
    "PortfolioStrategyBacktestConfigIn",
    "PortfolioStrategyRankingMetric",
    "PortfolioStrategyReentryMode",
    "PortfolioStrategyReentryReplacePolicy",
    "PortfolioStrategyReentryTrendFilter",
    "PortfolioStrategyReentryTrigger",
    "PortfolioStrategySizingMode",
]
