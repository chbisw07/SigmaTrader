from __future__ import annotations

import json
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.pydantic_compat import (
    PYDANTIC_V2,
    ConfigDict,
    field_validator,
    model_validator,
)

DistanceMode = Literal["ABS", "PCT", "ATR"]
ExitOrderType = Literal["MARKET"]


class DistanceSpec(BaseModel):
    enabled: bool = False
    mode: DistanceMode = "PCT"
    value: float = 0.0
    atr_period: int = 14
    atr_tf: str = "5m"

    if PYDANTIC_V2:
        model_config = ConfigDict(extra="forbid")

    @field_validator("value")
    @classmethod
    def _validate_value(cls, v: float) -> float:
        if v is None:
            return 0.0
        try:
            v = float(v)
        except Exception as err:
            raise ValueError("value must be a number") from err
        if v < 0:
            raise ValueError("value must be >= 0")
        return v

    @field_validator("atr_period")
    @classmethod
    def _validate_atr_period(cls, v: int) -> int:
        try:
            v = int(v)
        except Exception as err:
            raise ValueError("atr_period must be an integer") from err
        if v < 2:
            raise ValueError("atr_period must be >= 2")
        return v

    @field_validator("atr_tf")
    @classmethod
    def _validate_atr_tf(cls, v: str) -> str:
        v = str(v or "").strip()
        if not v:
            raise ValueError("atr_tf must be non-empty")
        allowed = {"1m", "5m", "15m", "30m", "1h", "1d"}
        if v not in allowed:
            raise ValueError(f"atr_tf must be one of {sorted(allowed)}")
        return v


class RiskSpec(BaseModel):
    stop_loss: DistanceSpec = Field(default_factory=DistanceSpec)
    trailing_stop: DistanceSpec = Field(default_factory=DistanceSpec)
    trailing_activation: DistanceSpec = Field(default_factory=DistanceSpec)
    exit_order_type: ExitOrderType = "MARKET"
    cooldown_ms: Optional[int] = None

    if PYDANTIC_V2:
        model_config = ConfigDict(extra="forbid")

    @field_validator("cooldown_ms")
    @classmethod
    def _validate_cooldown_ms(cls, v: int | None) -> int | None:
        if v is None:
            return None
        try:
            v = int(v)
        except Exception as err:
            raise ValueError("cooldown_ms must be an integer") from err
        if v < 0:
            raise ValueError("cooldown_ms must be >= 0")
        return v

    if PYDANTIC_V2:

        @model_validator(mode="after")
        def _validate_consistency(self) -> "RiskSpec":
            sl = self.stop_loss
            ts = self.trailing_stop
            act = self.trailing_activation

            if ts.enabled and not sl.enabled:
                raise ValueError("trailing_stop requires stop_loss to be enabled")
            if act.enabled and not ts.enabled:
                raise ValueError(
                    "trailing_activation requires trailing_stop to be enabled"
                )
            if sl.enabled and sl.value <= 0:
                raise ValueError("stop_loss.value must be > 0 when enabled")
            if ts.enabled and ts.value <= 0:
                raise ValueError("trailing_stop.value must be > 0 when enabled")
            if act.enabled and act.value <= 0:
                raise ValueError("trailing_activation.value must be > 0 when enabled")
            return self

    else:  # pragma: no cover - Pydantic v1 compatibility

        @model_validator(mode="after")
        def _validate_consistency(cls, values):  # type: ignore[no-redef]
            sl = values.get("stop_loss")
            ts = values.get("trailing_stop")
            act = values.get("trailing_activation")

            if ts and getattr(ts, "enabled", False) and not (sl and sl.enabled):
                raise ValueError("trailing_stop requires stop_loss to be enabled")
            if act and getattr(act, "enabled", False) and not (ts and ts.enabled):
                raise ValueError(
                    "trailing_activation requires trailing_stop to be enabled"
                )
            if sl and getattr(sl, "enabled", False) and float(sl.value or 0) <= 0:
                raise ValueError("stop_loss.value must be > 0 when enabled")
            if ts and getattr(ts, "enabled", False) and float(ts.value or 0) <= 0:
                raise ValueError("trailing_stop.value must be > 0 when enabled")
            if act and getattr(act, "enabled", False) and float(act.value or 0) <= 0:
                raise ValueError("trailing_activation.value must be > 0 when enabled")
            return values

    def to_json(self) -> str:
        if PYDANTIC_V2:
            return self.model_dump_json()
        return json.dumps(self.dict())

    @classmethod
    def from_json(cls, raw: str | None) -> "RiskSpec | None":
        if not raw:
            return None
        try:
            if PYDANTIC_V2:
                return cls.model_validate_json(raw)
            return cls.parse_raw(raw)
        except Exception:
            return None


class ManagedRiskPositionRead(BaseModel):
    id: int
    user_id: int | None
    entry_order_id: int
    exit_order_id: int | None
    exit_order_status: str | None
    broker_name: str
    symbol: str
    exchange: str
    product: str
    side: str
    qty: float
    execution_target: str
    entry_price: float
    stop_distance: float | None
    trail_distance: float | None
    activation_distance: float | None
    current_stop: float | None
    best_favorable_price: float
    trail_price: float | None
    is_trailing_active: bool
    last_ltp: float | None
    status: str
    exit_reason: str | None
    created_at: datetime
    updated_at: datetime
    risk_spec: RiskSpec | None

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover - Pydantic v1

        class Config:
            orm_mode = True


__all__ = [
    "DistanceMode",
    "ExitOrderType",
    "DistanceSpec",
    "RiskSpec",
    "ManagedRiskPositionRead",
]
