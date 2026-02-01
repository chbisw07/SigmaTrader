from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.pydantic_compat import PYDANTIC_V2
from app.schemas.backtests import UniverseSymbol
from app.schemas.backtests_portfolio import BrokerName, ProductType
from app.schemas.backtests_portfolio_strategy import (
    PortfolioStrategyAllocationMode,
    PortfolioStrategyRankingMetric,
    PortfolioStrategySizingMode,
)
from app.schemas.backtests_strategy import StrategyDirection, StrategyTimeframe

DeploymentKind = Literal["STRATEGY", "PORTFOLIO_STRATEGY"]
ExecutionTarget = Literal["PAPER", "LIVE"]
DeploymentStatus = Literal["STOPPED", "RUNNING", "PAUSED", "ERROR"]


class DeploymentUniverse(BaseModel):
    target_kind: Literal["SYMBOL", "GROUP"] = "SYMBOL"
    group_id: Optional[int] = None
    symbols: list[UniverseSymbol] = Field(default_factory=list)


class DailyViaIntradaySettings(BaseModel):
    enabled: bool = True
    base_timeframe: Literal["1m", "5m", "15m", "30m", "1h"] = "5m"
    proxy_close_hhmm: str = "15:25"
    buy_window_start_hhmm: str = "15:25"
    buy_window_end_hhmm: str = "15:30"
    sell_window_start_hhmm: str = "09:15"
    sell_window_end_hhmm: str = "09:20"
    timezone: str = "Asia/Kolkata"

    @classmethod
    def _validate_hhmm(cls, raw: str, *, field: str) -> str:
        s = (raw or "").strip()
        if not re.fullmatch(r"\d{2}:\d{2}", s):
            raise ValueError(f"{field} must be HH:MM.")
        hh = int(s[0:2])
        mm = int(s[3:5])
        if hh < 0 or hh > 23 or mm < 0 or mm > 59:
            raise ValueError(f"{field} must be a valid 24h HH:MM time.")
        return s

    def normalize(self) -> "DailyViaIntradaySettings":
        return DailyViaIntradaySettings(
            enabled=bool(self.enabled),
            base_timeframe=self.base_timeframe,
            proxy_close_hhmm=self._validate_hhmm(
                self.proxy_close_hhmm,
                field="proxy_close_hhmm",
            ),
            buy_window_start_hhmm=self._validate_hhmm(
                self.buy_window_start_hhmm, field="buy_window_start_hhmm"
            ),
            buy_window_end_hhmm=self._validate_hhmm(
                self.buy_window_end_hhmm, field="buy_window_end_hhmm"
            ),
            sell_window_start_hhmm=self._validate_hhmm(
                self.sell_window_start_hhmm, field="sell_window_start_hhmm"
            ),
            sell_window_end_hhmm=self._validate_hhmm(
                self.sell_window_end_hhmm, field="sell_window_end_hhmm"
            ),
            timezone=(self.timezone or "Asia/Kolkata").strip() or "Asia/Kolkata",
        )


class StrategyDeploymentConfigIn(BaseModel):
    timeframe: StrategyTimeframe = "1d"
    daily_via_intraday: Optional[DailyViaIntradaySettings] = None

    source_run_id: Optional[int] = None

    entry_dsl: str = Field(min_length=1)
    exit_dsl: str = Field(min_length=1)

    product: ProductType = "CNC"
    direction: StrategyDirection = "LONG"
    acknowledge_short_risk: bool = False

    enter_immediately_on_start: bool = False
    acknowledge_enter_immediately_risk: bool = False

    broker_name: BrokerName = "zerodha"
    execution_target: ExecutionTarget = "PAPER"

    initial_cash: float = Field(default=100000.0, ge=0.0)
    position_size_pct: float = Field(default=100.0, ge=0.0, le=100.0)

    stop_loss_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    take_profit_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    trailing_stop_pct: float = Field(default=0.0, ge=0.0, le=100.0)

    max_equity_dd_global_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    max_equity_dd_trade_pct: float = Field(default=0.0, ge=0.0, le=100.0)


class PortfolioStrategyDeploymentConfigIn(BaseModel):
    timeframe: StrategyTimeframe = "1d"
    daily_via_intraday: Optional[DailyViaIntradaySettings] = None

    source_run_id: Optional[int] = None

    entry_dsl: str = Field(min_length=1)
    exit_dsl: str = Field(min_length=1)

    product: ProductType = "CNC"
    direction: StrategyDirection = "LONG"
    acknowledge_short_risk: bool = False

    enter_immediately_on_start: bool = False
    acknowledge_enter_immediately_risk: bool = False

    broker_name: BrokerName = "zerodha"
    execution_target: ExecutionTarget = "PAPER"

    initial_cash: float = Field(default=100000.0, ge=0.0)
    max_open_positions: int = Field(default=10, ge=1, le=200)

    allocation_mode: PortfolioStrategyAllocationMode = "EQUAL"
    ranking_metric: PortfolioStrategyRankingMetric = "PERF_PCT"
    ranking_window: int = Field(default=5, ge=1, le=400)

    sizing_mode: PortfolioStrategySizingMode = "PCT_EQUITY"
    position_size_pct: float = Field(default=20.0, ge=0.0, le=100.0)
    fixed_cash_per_trade: float = Field(default=0.0, ge=0.0)

    min_holding_bars: int = Field(default=0, ge=0, le=10000)
    cooldown_bars: int = Field(default=0, ge=0, le=10000)
    max_symbol_alloc_pct: float = Field(default=0.0, ge=0.0, le=100.0)

    stop_loss_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    take_profit_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    trailing_stop_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    max_equity_dd_global_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    max_equity_dd_trade_pct: float = Field(default=0.0, ge=0.0, le=100.0)


class StrategyDeploymentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    kind: DeploymentKind
    enabled: bool = False
    universe: DeploymentUniverse = Field(default_factory=DeploymentUniverse)
    config: dict[str, Any] = Field(default_factory=dict)


class StrategyDeploymentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    enabled: Optional[bool] = None
    universe: Optional[DeploymentUniverse] = None
    config: Optional[dict[str, Any]] = None


class StrategyDeploymentStateRead(BaseModel):
    status: DeploymentStatus
    last_evaluated_at: Optional[datetime] = None
    next_evaluate_at: Optional[datetime] = None
    last_eval_at: Optional[datetime] = None
    last_eval_bar_end_ts: Optional[datetime] = None
    runtime_state: Optional[str] = None
    last_decision: Optional[str] = None
    last_decision_reason: Optional[str] = None
    next_eval_at: Optional[datetime] = None
    last_error: Optional[str] = None
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    resumed_at: Optional[datetime] = None
    pause_reason: Optional[str] = None
    exposure: Optional[dict[str, Any]] = None


class StrategyDeploymentPauseRequest(BaseModel):
    reason: Optional[str] = None


class StrategyDeploymentDirectionMismatchResolutionRequest(BaseModel):
    action: Literal["ADOPT_EXIT_ONLY", "FLATTEN_THEN_CONTINUE", "IGNORE"]


class StrategyDeploymentStateSummary(BaseModel):
    open_positions: int = 0
    positions: list[dict[str, Any]] = Field(default_factory=list)


class StrategyDeploymentRead(BaseModel):
    id: int
    owner_id: int
    name: str
    description: Optional[str] = None
    kind: DeploymentKind
    enabled: bool
    universe: DeploymentUniverse
    config: dict[str, Any]
    state: StrategyDeploymentStateRead
    state_summary: StrategyDeploymentStateSummary = Field(
        default_factory=StrategyDeploymentStateSummary
    )
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, obj) -> "StrategyDeploymentRead":
        universe: dict[str, Any] = {}
        config: dict[str, Any] = {}
        try:
            payload = json.loads(obj.config_json or "{}")
            universe = payload.get("universe") or {}
            config = payload.get("config") or {}
        except Exception:
            universe = {}
            config = {}

        state = getattr(obj, "state", None)
        exposure = None
        raw_exposure = getattr(state, "exposure_json", None)
        if raw_exposure:
            try:
                exposure = json.loads(raw_exposure)
            except Exception:
                exposure = None
        state_read = StrategyDeploymentStateRead(
            status=(getattr(state, "status", None) or "STOPPED"),
            last_evaluated_at=getattr(state, "last_evaluated_at", None),
            next_evaluate_at=getattr(state, "next_evaluate_at", None),
            last_eval_at=getattr(state, "last_eval_at", None),
            last_eval_bar_end_ts=getattr(state, "last_eval_bar_end_ts", None),
            runtime_state=getattr(state, "runtime_state", None),
            last_decision=getattr(state, "last_decision", None),
            last_decision_reason=getattr(state, "last_decision_reason", None),
            next_eval_at=getattr(state, "next_eval_at", None),
            last_error=getattr(state, "last_error", None),
            started_at=getattr(state, "started_at", None),
            stopped_at=getattr(state, "stopped_at", None),
            paused_at=getattr(state, "paused_at", None),
            resumed_at=getattr(state, "resumed_at", None),
            pause_reason=getattr(state, "pause_reason", None),
            exposure=exposure,
        )

        summary = StrategyDeploymentStateSummary()
        raw_state = getattr(state, "state_json", None)
        if raw_state:
            try:
                s = json.loads(raw_state)
                positions = s.get("positions")
                if isinstance(positions, list):
                    summary.positions = positions
                    summary.open_positions = len(positions)
                elif isinstance(positions, dict):
                    out: list[dict[str, Any]] = []
                    for key, pos in positions.items():
                        if not isinstance(pos, dict):
                            continue
                        qty = int(pos.get("qty") or 0)
                        if qty <= 0:
                            continue
                        out.append({"key": str(key), **pos})
                    summary.positions = out
                    summary.open_positions = len(out)
            except Exception:
                pass

        return cls(
            id=obj.id,
            owner_id=obj.owner_id,
            name=obj.name,
            description=obj.description,
            kind=obj.kind,
            enabled=bool(obj.enabled),
            universe=(
                DeploymentUniverse.model_validate(universe)
                if PYDANTIC_V2
                else DeploymentUniverse.parse_obj(universe)
            ),
            config=config,
            state=state_read,
            state_summary=summary,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class StrategyDeploymentActionRead(BaseModel):
    id: int
    deployment_id: int
    job_id: Optional[int] = None
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @classmethod
    def from_model(cls, obj) -> "StrategyDeploymentActionRead":
        payload: dict[str, Any] = {}
        raw = getattr(obj, "payload_json", None)
        if raw:
            try:
                val = json.loads(raw)
                if isinstance(val, dict):
                    payload = val
            except Exception:
                payload = {}
        return cls(
            id=int(obj.id),
            deployment_id=int(obj.deployment_id),
            job_id=(
                int(obj.job_id) if getattr(obj, "job_id", None) is not None else None
            ),
            kind=str(obj.kind or ""),
            payload=payload,
            created_at=obj.created_at,
        )


class StrategyDeploymentEventRead(BaseModel):
    id: int
    deployment_id: int
    job_id: Optional[int] = None
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @classmethod
    def from_model(cls, obj) -> "StrategyDeploymentEventRead":
        payload: dict[str, Any] = {}
        raw = getattr(obj, "payload_json", None)
        if raw:
            try:
                val = json.loads(raw)
                if isinstance(val, dict):
                    payload = val
            except Exception:
                payload = {}
        return cls(
            id=int(obj.id),
            deployment_id=int(obj.deployment_id),
            job_id=(
                int(obj.job_id) if getattr(obj, "job_id", None) is not None else None
            ),
            kind=str(obj.kind or ""),
            payload=payload,
            created_at=obj.created_at,
        )


class StrategyDeploymentJobsMetrics(BaseModel):
    job_counts: dict[str, int] = Field(default_factory=dict)
    oldest_pending_scheduled_for: Optional[datetime] = None
    latest_failed_updated_at: Optional[datetime] = None


__all__ = [
    "DailyViaIntradaySettings",
    "DeploymentKind",
    "DeploymentStatus",
    "DeploymentUniverse",
    "ExecutionTarget",
    "PortfolioStrategyDeploymentConfigIn",
    "StrategyDeploymentConfigIn",
    "StrategyDeploymentActionRead",
    "StrategyDeploymentEventRead",
    "StrategyDeploymentCreate",
    "StrategyDeploymentRead",
    "StrategyDeploymentJobsMetrics",
    "StrategyDeploymentStateRead",
    "StrategyDeploymentStateSummary",
    "StrategyDeploymentUpdate",
]
