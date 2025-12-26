from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

PortfolioBacktestMethod = Literal["TARGET_WEIGHTS", "ROTATION", "RISK_PARITY"]
RebalanceCadence = Literal["WEEKLY", "MONTHLY"]


class PortfolioBacktestConfigIn(BaseModel):
    timeframe: Literal["1d"] = "1d"
    start_date: date
    end_date: date

    method: PortfolioBacktestMethod = "TARGET_WEIGHTS"
    cadence: RebalanceCadence = "MONTHLY"

    initial_cash: float = Field(default=100000.0, gt=0.0)

    budget_pct: float = Field(default=100.0, ge=0.0, le=100.0)
    max_trades: int = Field(default=50, ge=1, le=1000)
    min_trade_value: float = Field(default=0.0, ge=0.0)

    slippage_bps: float = Field(default=0.0, ge=0.0, le=2000.0)
    charges_bps: float = Field(default=0.0, ge=0.0, le=2000.0)


__all__ = [
    "PortfolioBacktestConfigIn",
    "PortfolioBacktestMethod",
    "RebalanceCadence",
]
