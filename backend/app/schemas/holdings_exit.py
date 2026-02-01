from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.holdings_exit.constants import (
    HOLDING_EXIT_DISPATCH_MODES,
    HOLDING_EXIT_EXECUTION_TARGETS,
    HOLDING_EXIT_ORDER_TYPES,
    HOLDING_EXIT_PRICE_SOURCES,
    HOLDING_EXIT_SIZE_MODES,
    HOLDING_EXIT_TRIGGER_KINDS,
)
from app.pydantic_compat import PYDANTIC_V2, ConfigDict, field_validator

HoldingExitStatus = Literal[
    "ACTIVE",
    "PAUSED",
    "TRIGGERED_PENDING",
    "ORDER_CREATED",
    "COMPLETED",
    "ERROR",
]
HoldingExitTriggerKind = Literal[
    "TARGET_ABS_PRICE",
    "TARGET_PCT_FROM_AVG_BUY",
    "DRAWDOWN_ABS_PRICE",
    "DRAWDOWN_PCT_FROM_PEAK",
]
HoldingExitSizeMode = Literal["ABS_QTY", "PCT_OF_POSITION"]
HoldingExitDispatchMode = Literal["MANUAL", "AUTO"]
HoldingExitExecutionTarget = Literal["LIVE", "PAPER"]
HoldingExitPriceSource = Literal["LTP"]
HoldingExitOrderType = Literal["MARKET"]


class HoldingExitSubscriptionCreate(BaseModel):
    broker_name: str = "zerodha"
    symbol: str = Field(min_length=1, max_length=128)
    exchange: str = "NSE"
    product: Literal["CNC", "MIS"] = "CNC"

    trigger_kind: HoldingExitTriggerKind
    trigger_value: float
    price_source: HoldingExitPriceSource = "LTP"

    size_mode: HoldingExitSizeMode
    size_value: float
    min_qty: int = 1

    order_type: HoldingExitOrderType = "MARKET"
    dispatch_mode: HoldingExitDispatchMode = "MANUAL"
    execution_target: HoldingExitExecutionTarget = "LIVE"

    cooldown_seconds: int = 300

    if PYDANTIC_V2:
        model_config = ConfigDict(extra="forbid")

    @field_validator("broker_name", "exchange", "symbol")
    @classmethod
    def _strip(cls, v: str) -> str:
        return str(v or "").strip()

    @field_validator("trigger_kind")
    @classmethod
    def _validate_trigger_kind(cls, v: str) -> str:
        v = str(v or "").strip().upper()
        if v not in set(HOLDING_EXIT_TRIGGER_KINDS):
            raise ValueError("Invalid trigger_kind.")
        return v

    @field_validator("price_source")
    @classmethod
    def _validate_price_source(cls, v: str) -> str:
        v = str(v or "").strip().upper()
        if v not in set(HOLDING_EXIT_PRICE_SOURCES):
            raise ValueError("Invalid price_source.")
        return v

    @field_validator("size_mode")
    @classmethod
    def _validate_size_mode(cls, v: str) -> str:
        v = str(v or "").strip().upper()
        if v not in set(HOLDING_EXIT_SIZE_MODES):
            raise ValueError("Invalid size_mode.")
        return v

    @field_validator("dispatch_mode")
    @classmethod
    def _validate_dispatch_mode(cls, v: str) -> str:
        v = str(v or "").strip().upper()
        if v not in set(HOLDING_EXIT_DISPATCH_MODES):
            raise ValueError("Invalid dispatch_mode.")
        return v

    @field_validator("execution_target")
    @classmethod
    def _validate_execution_target(cls, v: str) -> str:
        v = str(v or "").strip().upper()
        if v not in set(HOLDING_EXIT_EXECUTION_TARGETS):
            raise ValueError("Invalid execution_target.")
        return v

    @field_validator("order_type")
    @classmethod
    def _validate_order_type(cls, v: str) -> str:
        v = str(v or "").strip().upper()
        if v not in set(HOLDING_EXIT_ORDER_TYPES):
            raise ValueError("Invalid order_type.")
        return v

    @field_validator("trigger_value")
    @classmethod
    def _validate_trigger_value(cls, v: float) -> float:
        try:
            fv = float(v)
        except Exception as err:
            raise ValueError("trigger_value must be a number") from err
        return fv

    @field_validator("size_value")
    @classmethod
    def _validate_size_value(cls, v: float) -> float:
        try:
            fv = float(v)
        except Exception as err:
            raise ValueError("size_value must be a number") from err
        return fv

    @field_validator("min_qty", "cooldown_seconds")
    @classmethod
    def _validate_ints(cls, v: int) -> int:
        try:
            iv = int(v)
        except Exception as err:
            raise ValueError("Value must be an integer") from err
        return iv


class HoldingExitSubscriptionPatch(BaseModel):
    # Mutable fields (MVP). Scope fields are immutable to keep state predictable.
    trigger_kind: Optional[HoldingExitTriggerKind] = None
    trigger_value: Optional[float] = None
    price_source: Optional[HoldingExitPriceSource] = None

    size_mode: Optional[HoldingExitSizeMode] = None
    size_value: Optional[float] = None
    min_qty: Optional[int] = None

    dispatch_mode: Optional[HoldingExitDispatchMode] = None
    execution_target: Optional[HoldingExitExecutionTarget] = None
    cooldown_seconds: Optional[int] = None

    if PYDANTIC_V2:
        model_config = ConfigDict(extra="forbid")


class HoldingExitSubscriptionRead(BaseModel):
    id: int
    user_id: int | None
    broker_name: str
    symbol: str
    exchange: str
    product: str

    trigger_kind: str
    trigger_value: float
    price_source: str

    size_mode: str
    size_value: float
    min_qty: int

    order_type: str
    dispatch_mode: str
    execution_target: str

    status: str
    pending_order_id: int | None
    last_error: str | None
    last_evaluated_at: datetime | None
    last_triggered_at: datetime | None
    next_eval_at: datetime | None
    cooldown_seconds: int
    cooldown_until: datetime | None
    trigger_key: str | None

    created_at: datetime
    updated_at: datetime

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover

        class Config:
            orm_mode = True


class HoldingExitEventRead(BaseModel):
    id: int
    subscription_id: int
    event_type: str
    event_ts: datetime
    details: dict[str, Any] = Field(default_factory=dict)
    price_snapshot: dict[str, Any] | None = None
    created_at: datetime

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover

        class Config:
            orm_mode = True

    @classmethod
    def from_model(cls, obj) -> "HoldingExitEventRead":
        details: dict[str, Any] = {}
        price_snapshot: dict[str, Any] | None = None
        raw = getattr(obj, "details_json", None)
        if raw:
            try:
                val = json.loads(raw)
                if isinstance(val, dict):
                    details = val
            except Exception:
                details = {}
        raw_px = getattr(obj, "price_snapshot_json", None)
        if raw_px:
            try:
                val = json.loads(raw_px)
                if isinstance(val, dict):
                    price_snapshot = val
            except Exception:
                price_snapshot = None
        return cls(
            id=int(obj.id),
            subscription_id=int(obj.subscription_id),
            event_type=str(obj.event_type or ""),
            event_ts=obj.event_ts,
            details=details,
            price_snapshot=price_snapshot,
            created_at=obj.created_at,
        )


def validate_mvp_create(payload: HoldingExitSubscriptionCreate) -> None:
    """Additional MVP-only rules that depend on multiple fields."""

    # Conservative posture: MVP supports only CNC exits and manual queue.
    if str(payload.product).strip().upper() != "CNC":
        raise ValueError("Only product=CNC is supported for holdings exits (MVP).")
    if str(payload.dispatch_mode).strip().upper() != "MANUAL":
        raise ValueError("dispatch_mode=AUTO is not supported (MVP).")
    if str(payload.order_type).strip().upper() != "MARKET":
        raise ValueError("Only MARKET order_type is supported (MVP).")
    if str(payload.price_source).strip().upper() != "LTP":
        raise ValueError("Only LTP price_source is supported (MVP).")

    trigger_kind = str(payload.trigger_kind).strip().upper()
    if trigger_kind not in {"TARGET_ABS_PRICE", "TARGET_PCT_FROM_AVG_BUY"}:
        raise ValueError(
            "Only TARGET_ABS_PRICE and TARGET_PCT_FROM_AVG_BUY are supported (MVP).",
        )

    tv = float(payload.trigger_value or 0.0)
    if trigger_kind == "TARGET_ABS_PRICE":
        if tv <= 0:
            raise ValueError("trigger_value must be > 0 for TARGET_ABS_PRICE.")
    elif trigger_kind == "TARGET_PCT_FROM_AVG_BUY":
        if tv <= 0 or tv > 1000:
            raise ValueError(
                "trigger_value must be in (0, 1000] for TARGET_PCT_FROM_AVG_BUY.",
            )

    size_mode = str(payload.size_mode).strip().upper()
    sv = float(payload.size_value or 0.0)
    if size_mode == "ABS_QTY":
        if sv <= 0 or int(sv) != sv:
            raise ValueError("size_value must be a positive integer for ABS_QTY.")
    elif size_mode == "PCT_OF_POSITION":
        if sv <= 0 or sv > 100:
            raise ValueError("size_value must be in (0, 100] for PCT_OF_POSITION.")
    else:
        raise ValueError("Invalid size_mode.")

    if int(payload.min_qty or 0) <= 0:
        raise ValueError("min_qty must be >= 1.")
    if int(payload.cooldown_seconds or 0) < 0:
        raise ValueError("cooldown_seconds must be >= 0.")


def validate_mvp_patch(payload: HoldingExitSubscriptionPatch) -> None:
    if payload.dispatch_mode is not None:
        if str(payload.dispatch_mode).strip().upper() != "MANUAL":
            raise ValueError("dispatch_mode=AUTO is not supported (MVP).")
    if payload.execution_target is not None:
        if str(payload.execution_target).strip().upper() not in {"LIVE", "PAPER"}:
            raise ValueError("Invalid execution_target.")
    if payload.trigger_kind is not None:
        tk = str(payload.trigger_kind).strip().upper()
        if tk not in {"TARGET_ABS_PRICE", "TARGET_PCT_FROM_AVG_BUY"}:
            raise ValueError(
                (
                    "Only TARGET_ABS_PRICE and TARGET_PCT_FROM_AVG_BUY "
                    "are supported (MVP)."
                ),
            )
    if payload.trigger_value is not None:
        try:
            float(payload.trigger_value)
        except Exception as err:
            raise ValueError("trigger_value must be a number.") from err
    if payload.size_mode is not None:
        sm = str(payload.size_mode).strip().upper()
        if sm not in {"ABS_QTY", "PCT_OF_POSITION"}:
            raise ValueError("Invalid size_mode.")
    if payload.size_value is not None:
        try:
            float(payload.size_value)
        except Exception as err:
            raise ValueError("size_value must be a number.") from err


__all__ = [
    "HoldingExitStatus",
    "HoldingExitTriggerKind",
    "HoldingExitSizeMode",
    "HoldingExitDispatchMode",
    "HoldingExitExecutionTarget",
    "HoldingExitPriceSource",
    "HoldingExitOrderType",
    "HoldingExitSubscriptionCreate",
    "HoldingExitSubscriptionPatch",
    "HoldingExitSubscriptionRead",
    "HoldingExitEventRead",
    "validate_mvp_create",
    "validate_mvp_patch",
]
