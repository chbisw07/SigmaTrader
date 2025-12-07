from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.pydantic_compat import PYDANTIC_V2, ConfigDict

RiskScope = Literal["GLOBAL", "STRATEGY"]
ClampMode = Literal["CLAMP", "REJECT"]


class RiskSettingsBase(BaseModel):
    scope: RiskScope = "STRATEGY"
    strategy_id: Optional[int] = None

    max_order_value: Optional[float] = None
    max_quantity_per_order: Optional[float] = None
    max_daily_loss: Optional[float] = None
    allow_short_selling: bool = True
    max_open_positions: Optional[int] = None
    clamp_mode: ClampMode = "CLAMP"

    symbol_whitelist: Optional[str] = None
    symbol_blacklist: Optional[str] = None

    if PYDANTIC_V2:
        from pydantic import model_validator

        @model_validator(mode="after")
        def validate_scope_and_strategy(self) -> "RiskSettingsBase":
            scope = self.scope
            strategy_id = self.strategy_id
            if scope == "GLOBAL" and strategy_id is not None:
                raise ValueError(
                    "GLOBAL risk settings must not reference a strategy_id",
                )
            if scope == "STRATEGY" and strategy_id is None:
                raise ValueError(
                    "STRATEGY risk settings require a strategy_id",
                )
            return self

    else:  # pragma: no cover - Pydantic v1
        from pydantic import root_validator

        @root_validator(skip_on_failure=True)
        def validate_scope_and_strategy(cls, values: dict) -> dict:
            scope = values.get("scope")
            strategy_id = values.get("strategy_id")
            if scope == "GLOBAL" and strategy_id is not None:
                raise ValueError(
                    "GLOBAL risk settings must not reference a strategy_id",
                )
            if scope == "STRATEGY" and strategy_id is None:
                raise ValueError(
                    "STRATEGY risk settings require a strategy_id",
                )
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
    clamp_mode: Optional[ClampMode] = Field(None)

    symbol_whitelist: Optional[Optional[str]] = Field(None)
    symbol_blacklist: Optional[Optional[str]] = Field(None)


class RiskSettingsRead(RiskSettingsBase):
    id: int

    if PYDANTIC_V2:
        # model_config is enough for Pydantic v2; Pydantic v1 ignores it.
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover - Pydantic v1

        class Config:
            orm_mode = True


__all__ = [
    "RiskScope",
    "RiskSettingsCreate",
    "RiskSettingsUpdate",
    "RiskSettingsRead",
]
