from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.pydantic_compat import PYDANTIC_V2, ConfigDict, model_validator

RebalanceBrokerScope = Literal["zerodha", "angelone", "both"]
RebalanceMode = Literal["MANUAL", "AUTO"]
RebalanceTargetKind = Literal["GROUP", "HOLDINGS"]
RebalanceMethod = Literal["TARGET_WEIGHT", "SIGNAL_ROTATION", "RISK_PARITY"]
RebalanceRotationWeighting = Literal["EQUAL", "SCORE", "RANK"]
RebalanceRiskWindow = Literal["6M", "1Y"]


class RebalanceRiskConfig(BaseModel):
    """Risk-based target derivation config (v3).

    Uses daily close returns to estimate a covariance matrix over a lookback
    window, then derives equal risk contribution (risk parity / ERC) weights.
    """

    window: RebalanceRiskWindow = "6M"
    timeframe: Literal["1d"] = "1d"
    min_observations: int = Field(60, ge=10, le=2000)

    min_weight: float = Field(0.0, ge=0.0, le=1.0)
    max_weight: float = Field(1.0, ge=0.0, le=1.0)

    max_iter: int = Field(2000, ge=10, le=20000)
    tol: float = Field(1e-8, gt=0.0, lt=1.0)

    @model_validator(mode="before")
    def _validate_bounds(cls, values):  # type: ignore[no-untyped-def]
        if not isinstance(values, dict):
            return values
        mn = values.get("min_weight", 0.0)
        mx = values.get("max_weight", 1.0)
        try:
            mn_f = float(mn)
            mx_f = float(mx)
        except Exception:
            return values
        if mn_f > mx_f:
            raise ValueError("min_weight cannot be greater than max_weight.")
        return values


class RebalanceRotationConfig(BaseModel):
    """Signal/strategy-driven rotation config (v2).

    Notes:
    - Requires an OVERLAY output (numeric) for ranking.
    - When both universe_group_id and screener_run_id are omitted, the rebalance
      group's members are used as the candidate universe.
    """

    signal_strategy_version_id: int = Field(..., ge=1)
    signal_output: str = Field(..., min_length=1, max_length=64)
    signal_params: Dict[str, Any] = Field(default_factory=dict)

    universe_group_id: Optional[int] = Field(None, ge=1)
    screener_run_id: Optional[int] = Field(None, ge=1)

    top_n: int = Field(10, ge=1, le=500)
    weighting: RebalanceRotationWeighting = "EQUAL"

    sell_not_in_top_n: bool = True

    min_price: Optional[float] = Field(None, ge=0.0)
    min_avg_volume_20d: Optional[float] = Field(None, ge=0.0)

    symbol_whitelist: List[str] = Field(default_factory=list)
    symbol_blacklist: List[str] = Field(default_factory=list)

    require_positive_score: bool = True

    @model_validator(mode="before")
    def _validate_universe(cls, values):  # type: ignore[no-untyped-def]
        if not isinstance(values, dict):
            return values
        if values.get("universe_group_id") and values.get("screener_run_id"):
            raise ValueError(
                "Provide only one of universe_group_id or screener_run_id."
            )
        return values


class RebalancePreviewRequest(BaseModel):
    target_kind: RebalanceTargetKind = "GROUP"
    group_id: Optional[int] = Field(
        None,
        ge=1,
        description="Required when target_kind=GROUP.",
    )
    broker_name: RebalanceBrokerScope = "zerodha"
    rebalance_method: RebalanceMethod = "TARGET_WEIGHT"
    rotation: Optional[RebalanceRotationConfig] = None
    risk: Optional[RebalanceRiskConfig] = None

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
        rebalance_method = values.get("rebalance_method") or "TARGET_WEIGHT"
        rotation = values.get("rotation")
        if str(rebalance_method).upper() == "SIGNAL_ROTATION":
            if str(target_kind).upper() != "GROUP":
                raise ValueError(
                    "rebalance_method=SIGNAL_ROTATION requires target_kind=GROUP."
                )
            if rotation is None:
                raise ValueError(
                    "rotation config is required when rebalance_method=SIGNAL_ROTATION."
                )
        if str(rebalance_method).upper() == "RISK_PARITY":
            if str(target_kind).upper() != "GROUP":
                raise ValueError(
                    "rebalance_method=RISK_PARITY requires target_kind=GROUP."
                )
            if values.get("risk") is None:
                raise ValueError(
                    "risk config is required when rebalance_method=RISK_PARITY."
                )
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

    reason: Dict[str, object] = Field(default_factory=dict)


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
    derived_targets: Optional[List[Dict[str, object]]] = None


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
    "RebalanceMethod",
    "RebalanceRotationWeighting",
    "RebalanceRotationConfig",
    "RebalanceRiskConfig",
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
