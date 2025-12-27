from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

PortfolioBacktestMethod = Literal["TARGET_WEIGHTS", "ROTATION", "RISK_PARITY"]
RebalanceCadence = Literal["WEEKLY", "MONTHLY"]
FillTiming = Literal["CLOSE", "NEXT_OPEN"]
ProductType = Literal["CNC", "MIS"]
ChargesModel = Literal["BPS", "BROKER"]
BrokerName = Literal["zerodha", "angelone"]


class PortfolioBacktestConfigIn(BaseModel):
    timeframe: Literal["1d"] = "1d"
    start_date: date
    end_date: date

    method: PortfolioBacktestMethod = "TARGET_WEIGHTS"
    cadence: RebalanceCadence = "MONTHLY"
    fill_timing: FillTiming = "CLOSE"

    initial_cash: float = Field(default=100000.0, ge=0.0)

    budget_pct: float = Field(default=100.0, ge=0.0, le=100.0)
    max_trades: int = Field(default=50, ge=1, le=1000)
    min_trade_value: float = Field(default=0.0, ge=0.0)

    slippage_bps: float = Field(default=0.0, ge=0.0, le=2000.0)
    charges_bps: float = Field(default=0.0, ge=0.0, le=2000.0)
    charges_model: ChargesModel = "BPS"
    charges_broker: BrokerName = "zerodha"
    product: ProductType = "CNC"
    include_dp_charges: bool = True

    # Rotation (v2): Top-N momentum with optional eligibility filter.
    top_n: int = Field(default=10, ge=1, le=200)
    ranking_window: int = Field(default=20, ge=1, le=400)
    eligible_dsl: str = ""

    # Risk parity (v3): rolling covariance-based weights (equal risk contribution).
    risk_window: int = Field(default=126, ge=2, le=400)
    min_observations: int = Field(default=60, ge=2, le=400)
    min_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    max_weight: float = Field(default=1.0, ge=0.0, le=1.0)


__all__ = [
    "BrokerName",
    "ChargesModel",
    "FillTiming",
    "PortfolioBacktestConfigIn",
    "PortfolioBacktestMethod",
    "ProductType",
    "RebalanceCadence",
]
