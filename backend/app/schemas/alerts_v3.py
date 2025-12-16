from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.pydantic_compat import PYDANTIC_V2, ConfigDict


class AlertVariableDef(BaseModel):
    name: str = Field(..., min_length=1)
    # MVP: allow either free-form DSL or structured kind/params
    # (compiler supports both).
    dsl: Optional[str] = None
    kind: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


class AlertDefinitionCreate(BaseModel):
    name: str = Field(..., min_length=1)
    target_kind: str = Field(..., min_length=1)
    target_ref: str = Field(..., min_length=1)
    exchange: Optional[str] = None

    evaluation_cadence: Optional[str] = None
    variables: List[AlertVariableDef] = Field(default_factory=list)
    condition_dsl: str = Field(..., min_length=1)

    trigger_mode: str = Field(default="ONCE_PER_BAR")
    throttle_seconds: Optional[int] = Field(default=None, ge=1)
    only_market_hours: bool = False
    expires_at: Optional[datetime] = None
    enabled: bool = True


class AlertDefinitionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    target_kind: Optional[str] = None
    target_ref: Optional[str] = None
    exchange: Optional[str] = None

    evaluation_cadence: Optional[str] = None
    variables: Optional[List[AlertVariableDef]] = None
    condition_dsl: Optional[str] = None

    trigger_mode: Optional[str] = None
    throttle_seconds: Optional[int] = Field(default=None, ge=1)
    only_market_hours: Optional[bool] = None
    expires_at: Optional[datetime] = None
    enabled: Optional[bool] = None


class AlertDefinitionRead(BaseModel):
    id: int
    name: str
    target_kind: str
    target_ref: str
    exchange: Optional[str] = None

    evaluation_cadence: str
    variables: List[AlertVariableDef] = Field(default_factory=list)
    condition_dsl: str

    trigger_mode: str
    throttle_seconds: Optional[int] = None
    only_market_hours: bool
    expires_at: Optional[datetime] = None
    enabled: bool

    last_evaluated_at: Optional[datetime] = None
    last_triggered_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover

        class Config:
            orm_mode = True


class CustomIndicatorCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    params: List[str] = Field(default_factory=list)
    body_dsl: str = Field(..., min_length=1)
    enabled: bool = True


class CustomIndicatorUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = None
    params: Optional[List[str]] = None
    body_dsl: Optional[str] = None
    enabled: Optional[bool] = None


class CustomIndicatorRead(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    params: List[str] = Field(default_factory=list)
    body_dsl: str
    enabled: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover

        class Config:
            orm_mode = True


class AlertEventRead(BaseModel):
    id: int
    alert_definition_id: int
    symbol: str
    exchange: Optional[str] = None
    evaluation_cadence: Optional[str] = None
    reason: Optional[str] = None
    snapshot: Dict[str, Any] = Field(default_factory=dict)
    triggered_at: datetime
    bar_time: Optional[datetime] = None

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover

        class Config:
            orm_mode = True


class AlertV3TestRequest(BaseModel):
    target_kind: str = Field(..., min_length=1)
    target_ref: str = Field(..., min_length=1)
    exchange: Optional[str] = None

    evaluation_cadence: Optional[str] = None
    variables: List[AlertVariableDef] = Field(default_factory=list)
    condition_dsl: str = Field(..., min_length=1)


class AlertV3TestResult(BaseModel):
    symbol: str
    exchange: str
    matched: bool
    bar_time: Optional[datetime] = None
    snapshot: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class AlertV3TestResponse(BaseModel):
    evaluation_cadence: str
    results: List[AlertV3TestResult] = Field(default_factory=list)


__all__ = [
    "AlertVariableDef",
    "AlertDefinitionCreate",
    "AlertDefinitionUpdate",
    "AlertDefinitionRead",
    "CustomIndicatorCreate",
    "CustomIndicatorUpdate",
    "CustomIndicatorRead",
    "AlertEventRead",
    "AlertV3TestRequest",
    "AlertV3TestResult",
    "AlertV3TestResponse",
]
