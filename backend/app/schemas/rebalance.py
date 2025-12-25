from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.pydantic_compat import PYDANTIC_V2, ConfigDict, model_validator

RebalanceBrokerScope = Literal["zerodha", "angelone", "both"]
RebalanceMode = Literal["MANUAL", "AUTO"]
RebalanceTargetKind = Literal["GROUP", "HOLDINGS"]


class RebalancePreviewRequest(BaseModel):
    target_kind: RebalanceTargetKind = "GROUP"
    group_id: Optional[int] = Field(
        None,
        ge=1,
        description="Required when target_kind=GROUP.",
    )
    broker_name: RebalanceBrokerScope = "zerodha"

    budget_pct: Optional[float] = Field(
        0.10,
        ge=0.0,
        le=1.0,
        description="Fraction of portfolio value to rebalance (0.0 to 1.0).",
    )
    budget_amount: Optional[float] = Field(
        None,
        ge=0.0,
        description="Absolute INR budget; overrides budget_pct when set.",
    )

    drift_band_abs_pct: float = Field(
        0.02,
        ge=0.0,
        le=1.0,
        description="Absolute drift band (fraction).",
    )
    drift_band_rel_pct: float = Field(
        0.15,
        ge=0.0,
        le=1.0,
        description="Relative drift band as fraction of target weight.",
    )

    max_trades: int = Field(10, ge=0, le=200)
    min_trade_value: float = Field(2000.0, ge=0.0)

    @model_validator(mode="before")
    def _validate_group_id(cls, values):  # type: ignore[no-untyped-def]
        # Pydantic v1 compatibility: root_validator signature is (cls, values).
        if not isinstance(values, dict):
            return values
        target_kind = values.get("target_kind") or "GROUP"
        group_id = values.get("group_id")
        if str(target_kind).upper() == "GROUP":
            if group_id is None:
                raise ValueError("group_id is required when target_kind=GROUP.")
        return values


class RebalanceTrade(BaseModel):
    symbol: str
    exchange: Optional[str] = None
    side: Literal["BUY", "SELL"]
    qty: int
    estimated_price: float
    estimated_notional: float

    target_weight: float
    live_weight: float
    drift: float
    current_value: float
    desired_value: float
    delta_value: float
    scale: float

    reason: Dict[str, object] = {}


class RebalancePreviewSummary(BaseModel):
    portfolio_value: float
    budget: float
    scale: float

    total_buy_value: float
    total_sell_value: float
    turnover_pct: float
    budget_used: float
    budget_used_pct: float

    max_abs_drift_before: float
    max_abs_drift_after: float
    trades_count: int


class RebalancePreviewResult(BaseModel):
    target_kind: RebalanceTargetKind = "GROUP"
    group_id: Optional[int] = None
    broker_name: Literal["zerodha", "angelone"]
    trades: List[RebalanceTrade] = []
    summary: RebalancePreviewSummary
    warnings: List[str] = []


class RebalancePreviewResponse(BaseModel):
    results: List[RebalancePreviewResult]


class RebalanceExecuteRequest(RebalancePreviewRequest):
    mode: RebalanceMode = "MANUAL"
    execution_target: Literal["LIVE", "PAPER"] = "LIVE"
    order_type: Literal["MARKET", "LIMIT"] = "MARKET"
    product: Literal["CNC", "MIS"] = "CNC"
    idempotency_key: Optional[str] = Field(None, max_length=128)


class RebalanceRunOrderRead(BaseModel):
    id: int
    run_id: int
    order_id: Optional[int] = None
    symbol: str
    exchange: Optional[str] = None
    side: str
    qty: float
    estimated_price: Optional[float] = None
    estimated_notional: Optional[float] = None
    status: str
    created_at: datetime

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover

        class Config:
            orm_mode = True


class RebalanceRunRead(BaseModel):
    id: int
    owner_id: Optional[int] = None
    group_id: int
    broker_name: str
    status: str
    mode: str
    idempotency_key: Optional[str] = None
    summary_json: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    executed_at: Optional[datetime] = None
    orders: List[RebalanceRunOrderRead] = []

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover

        class Config:
            orm_mode = True


class RebalanceExecuteResult(BaseModel):
    run: Optional[RebalanceRunRead] = None
    created_order_ids: List[int] = []


class RebalanceExecuteResponse(BaseModel):
    results: List[RebalanceExecuteResult]


__all__ = [
    "RebalanceBrokerScope",
    "RebalanceMode",
    "RebalanceTargetKind",
    "RebalancePreviewRequest",
    "RebalancePreviewResponse",
    "RebalancePreviewResult",
    "RebalanceTrade",
    "RebalancePreviewSummary",
    "RebalanceExecuteRequest",
    "RebalanceExecuteResponse",
    "RebalanceExecuteResult",
    "RebalanceRunRead",
    "RebalanceRunOrderRead",
]
