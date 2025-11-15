from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, root_validator

RiskScope = Literal["GLOBAL", "STRATEGY"]


class RiskSettingsBase(BaseModel):
    scope: RiskScope = "STRATEGY"
    strategy_id: Optional[int] = None

    max_order_value: Optional[float] = None
    max_quantity_per_order: Optional[float] = None
    max_daily_loss: Optional[float] = None
    allow_short_selling: bool = True
    max_open_positions: Optional[int] = None
    clamp_mode: str = Field("CLAMP", regex="^(CLAMP|REJECT)$")

    symbol_whitelist: Optional[str] = None
    symbol_blacklist: Optional[str] = None

    @root_validator
    def validate_scope_and_strategy(cls, values: dict) -> dict:
        scope = values.get("scope")
        strategy_id = values.get("strategy_id")
        if scope == "GLOBAL" and strategy_id is not None:
            raise ValueError("GLOBAL risk settings must not reference a strategy_id")
        if scope == "STRATEGY" and strategy_id is None:
            raise ValueError("STRATEGY risk settings require a strategy_id")
        return values


class RiskSettingsCreate(RiskSettingsBase):
    pass


class RiskSettingsUpdate(BaseModel):
    scope: Optional[RiskScope] = None
    strategy_id: Optional[int] = None

    max_order_value: Optional[Optional[float]] = Field(None)
    max_quantity_per_order: Optional[Optional[float]] = Field(None)
    max_daily_loss: Optional[Optional[float]] = Field(None)
    allow_short_selling: Optional[bool] = None
    max_open_positions: Optional[Optional[int]] = Field(None)
    clamp_mode: Optional[str] = Field(None, regex="^(CLAMP|REJECT)$")

    symbol_whitelist: Optional[Optional[str]] = Field(None)
    symbol_blacklist: Optional[Optional[str]] = Field(None)


class RiskSettingsRead(RiskSettingsBase):
    id: int

    class Config:
        orm_mode = True


__all__ = [
    "RiskScope",
    "RiskSettingsCreate",
    "RiskSettingsUpdate",
    "RiskSettingsRead",
]
