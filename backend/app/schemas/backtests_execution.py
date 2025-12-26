from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.backtests_portfolio import FillTiming


class ExecutionBacktestConfigIn(BaseModel):
    """Execution backtest configuration.

    The execution backtest compares:
    - Ideal: same strategy/config, but frictionless fills at CLOSE
      (no charges/slippage).
    - Realistic: same strategy/config, but with selected fill timing + costs.
    """

    base_run_id: int = Field(ge=1)
    fill_timing: FillTiming = "NEXT_OPEN"
    slippage_bps: float = Field(default=0.0, ge=0.0, le=2000.0)
    charges_bps: float = Field(default=0.0, ge=0.0, le=2000.0)


ExecutionBacktestKind = Literal["EXECUTION"]

__all__ = ["ExecutionBacktestConfigIn", "ExecutionBacktestKind"]
