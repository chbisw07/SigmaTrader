from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class AiTmSchemaVersion(str, Enum):
    v1 = "v1"


class BrokerPosition(BaseModel):
    symbol: str
    product: str = "CNC"  # CNC/MIS
    qty: float
    avg_price: Optional[float] = None


class BrokerOrder(BaseModel):
    broker_order_id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    product: str = "CNC"
    qty: float
    order_type: str = "MARKET"
    status: str = "UNKNOWN"


class Quote(BaseModel):
    symbol: str
    last_price: float
    as_of_ts: datetime


class BrokerSnapshot(BaseModel):
    schema_version: AiTmSchemaVersion = AiTmSchemaVersion.v1
    as_of_ts: datetime
    account_id: str = "default"
    source: str = "stub"
    holdings: List[Dict[str, Any]] = Field(default_factory=list)
    positions: List[BrokerPosition] = Field(default_factory=list)
    orders: List[BrokerOrder] = Field(default_factory=list)
    margins: Dict[str, Any] = Field(default_factory=dict)
    quotes_cache: List[Quote] = Field(default_factory=list)


class LedgerPosition(BaseModel):
    symbol: str
    product: str = "CNC"
    expected_qty: float
    avg_price: Optional[float] = None


class LedgerOrder(BaseModel):
    order_id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    product: str = "CNC"
    qty: float
    order_type: str = "MARKET"
    status: str = "UNKNOWN"
    broker_order_id: Optional[str] = None


class LedgerSnapshot(BaseModel):
    schema_version: AiTmSchemaVersion = AiTmSchemaVersion.v1
    as_of_ts: datetime
    account_id: str = "default"
    expected_positions: List[LedgerPosition] = Field(default_factory=list)
    expected_orders: List[LedgerOrder] = Field(default_factory=list)
    watchers: List[Dict[str, Any]] = Field(default_factory=list)


class TradeIntent(BaseModel):
    schema_version: AiTmSchemaVersion = AiTmSchemaVersion.v1
    symbols: List[str]
    side: Literal["BUY", "SELL"]
    product: Literal["MIS", "CNC"] = "CNC"
    constraints: Dict[str, Any] = Field(default_factory=dict)
    risk_budget_pct: Optional[float] = None


class TradePlan(BaseModel):
    schema_version: AiTmSchemaVersion = AiTmSchemaVersion.v1
    plan_id: str
    intent: TradeIntent
    entry_rules: List[Dict[str, Any]] = Field(default_factory=list)
    sizing_method: str = "fixed"
    risk_model: Dict[str, Any] = Field(default_factory=dict)
    order_skeleton: Dict[str, Any] = Field(default_factory=dict)
    validity_window: Dict[str, Any] = Field(default_factory=dict)
    idempotency_scope: str = "account"


class RiskDecisionOutcome(str, Enum):
    allow = "allow"
    deny = "deny"


class RiskDecision(BaseModel):
    schema_version: AiTmSchemaVersion = AiTmSchemaVersion.v1
    outcome: RiskDecisionOutcome
    reasons: List[str] = Field(default_factory=list)
    reason_codes: List[Dict[str, Any]] = Field(default_factory=list)
    computed_risk_metrics: Dict[str, Any] = Field(default_factory=dict)
    policy_version: str = "v1"
    policy_hash: Optional[str] = None


class DecisionToolCall(BaseModel):
    tool_name: str
    input_summary: Dict[str, Any] = Field(default_factory=dict)
    output_summary: Dict[str, Any] = Field(default_factory=dict)
    duration_ms: Optional[int] = None


class DecisionTrace(BaseModel):
    schema_version: AiTmSchemaVersion = AiTmSchemaVersion.v1
    decision_id: str
    correlation_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    account_id: str = "default"
    user_message: str
    inputs_used: Dict[str, Any] = Field(default_factory=dict)
    tools_called: List[DecisionToolCall] = Field(default_factory=list)
    riskgate_result: Optional[RiskDecision] = None
    final_outcome: Dict[str, Any] = Field(default_factory=dict)
    explanations: List[str] = Field(default_factory=list)


class IdempotencyStatus(str, Enum):
    started = "STARTED"
    completed = "COMPLETED"
    failed = "FAILED"


class IdempotencyRecord(BaseModel):
    schema_version: AiTmSchemaVersion = AiTmSchemaVersion.v1
    account_id: str = "default"
    key: str
    status: IdempotencyStatus = IdempotencyStatus.started
    first_seen_ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload_hash: str
    result_json: Dict[str, Any] = Field(default_factory=dict)


class ReconciliationSeverity(str, Enum):
    low = "L"
    medium = "M"
    high = "H"


class ReconciliationDelta(BaseModel):
    schema_version: AiTmSchemaVersion = AiTmSchemaVersion.v1
    delta_type: str
    severity: ReconciliationSeverity
    key: str
    summary: str
    broker_ref: Dict[str, Any] = Field(default_factory=dict)
    expected_ref: Dict[str, Any] = Field(default_factory=dict)


class MonitorJob(BaseModel):
    schema_version: AiTmSchemaVersion = AiTmSchemaVersion.v1
    monitor_job_id: str
    account_id: str = "default"
    enabled: bool = True
    symbols: List[str]
    conditions: List[Dict[str, Any]] = Field(default_factory=list)
    cadence_sec: int = 60
    window: Dict[str, Any] = Field(default_factory=dict)


class AiTmMessageRole(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class AiTmMessage(BaseModel):
    message_id: str
    role: AiTmMessageRole
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    correlation_id: Optional[str] = None
    decision_id: Optional[str] = None


class AiTmThread(BaseModel):
    thread_id: str = "default"
    account_id: str = "default"
    messages: List[AiTmMessage] = Field(default_factory=list)


class AiTmUserMessageRequest(BaseModel):
    account_id: str = "default"
    content: str = Field(min_length=1, max_length=10_000)


class AiTmUserMessageResponse(BaseModel):
    thread: AiTmThread
    decision_id: str


class TradePlanCreateRequest(BaseModel):
    account_id: str = "default"
    intent: TradeIntent


class TradePlanCreateResponse(BaseModel):
    plan: TradePlan


class PlaybookCreateRequest(BaseModel):
    account_id: str = "default"
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=10_000)
    plan: TradePlan
    cadence_sec: Optional[int] = Field(default=None, ge=1)


class PlaybookRead(BaseModel):
    playbook_id: str
    account_id: str
    name: str
    description: Optional[str] = None
    plan_id: str
    enabled: bool
    armed: bool
    armed_at: Optional[datetime] = None
    armed_by_message_id: Optional[str] = None
    cadence_sec: Optional[int] = None
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class PlaybookRunRead(BaseModel):
    run_id: str
    playbook_id: str
    dedupe_key: str
    decision_id: Optional[str] = None
    authorization_message_id: Optional[str] = None
    status: str
    outcome: Dict[str, Any] = Field(default_factory=dict)
    started_at: datetime
    completed_at: Optional[datetime] = None


class PortfolioDriftItem(BaseModel):
    symbol: str
    product: str = "CNC"
    expected_qty: float
    broker_qty: float
    delta_qty: float
    last_price: Optional[float] = None


class TrendRegime(str, Enum):
    up = "up"
    down = "down"
    range = "range"
    unknown = "unknown"


class VolatilityRegime(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"
    unknown = "unknown"


class SymbolMarketContext(BaseModel):
    symbol: str
    exchange: str = "NSE"
    timeframe: str = "1d"
    as_of_ts: datetime
    close: Optional[float] = None
    sma20: Optional[float] = None
    sma50: Optional[float] = None
    atr14: Optional[float] = None
    atr14_pct: Optional[float] = None
    vol20_ann_pct: Optional[float] = None
    trend_regime: TrendRegime = TrendRegime.unknown
    volatility_regime: VolatilityRegime = VolatilityRegime.unknown
    notes: List[str] = Field(default_factory=list)


class MarketContextOverlay(BaseModel):
    as_of_ts: datetime
    exchange: str = "NSE"
    timeframe: str = "1d"
    items: List[SymbolMarketContext] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)


class PortfolioDiagnostics(BaseModel):
    as_of_ts: datetime
    account_id: str = "default"
    drift: List[PortfolioDriftItem] = Field(default_factory=list)
    risk_budgets: Dict[str, Any] = Field(default_factory=dict)
    correlation: Dict[str, Any] = Field(default_factory=dict)
    market_context: Optional[MarketContextOverlay] = None


class MarketContextResponse(BaseModel):
    overlay: MarketContextOverlay


class SizingSuggestRequest(BaseModel):
    account_id: str = "default"
    symbol: str = Field(min_length=1, max_length=128)
    exchange: str = "NSE"
    product: Literal["MIS", "CNC"] = "CNC"
    entry_price: float = Field(gt=0)
    stop_price: float = Field(gt=0)
    risk_budget_pct: float = Field(gt=0, le=10)
    equity_value: Optional[float] = Field(default=None, gt=0)
    max_qty: Optional[int] = Field(default=None, ge=1)


class SizingSuggestResponse(BaseModel):
    symbol: str
    exchange: str
    entry_price: float
    stop_price: float
    risk_budget_pct: float
    equity_value: float
    risk_per_share: float
    risk_amount: float
    suggested_qty: int
    notional_value: float
    notes: List[str] = Field(default_factory=list)
