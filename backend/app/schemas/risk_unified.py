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


__all__ = ["RiskProduct", "RiskSourceBucket", "UnifiedRiskGlobalRead", "UnifiedRiskGlobalUpdate"]

