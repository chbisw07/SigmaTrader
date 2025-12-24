from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.pydantic_compat import PYDANTIC_V2, ConfigDict
from app.schemas.alerts_v3 import AlertVariableDef

SignalStrategyScope = Literal["USER", "GLOBAL"]
SignalStrategyOutputKind = Literal["SIGNAL", "OVERLAY"]
SignalStrategyRegime = Literal["BULL", "SIDEWAYS", "BEAR"]
SignalStrategyParamType = Literal["number", "string", "bool", "enum", "timeframe"]


class SignalStrategyInputDef(BaseModel):
    name: str = Field(..., min_length=1)
    type: SignalStrategyParamType
    default: Optional[Any] = None
    enum_values: Optional[List[str]] = None


class SignalStrategyOutputDef(BaseModel):
    name: str = Field(..., min_length=1)
    kind: SignalStrategyOutputKind
    dsl: str = Field(..., min_length=1)
    # For overlays: hints for chart placement. (Non-binding.)
    plot: Optional[str] = None


class SignalStrategyVersionCreate(BaseModel):
    inputs: List[SignalStrategyInputDef] = Field(default_factory=list)
    variables: List[AlertVariableDef] = Field(default_factory=list)
    outputs: List[SignalStrategyOutputDef] = Field(default_factory=list)
    enabled: bool = True


class SignalStrategyCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    regimes: List[SignalStrategyRegime] = Field(default_factory=list)
    scope: SignalStrategyScope = "USER"
    version: SignalStrategyVersionCreate


class SignalStrategyUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    regimes: Optional[List[SignalStrategyRegime]] = None
    scope: Optional[SignalStrategyScope] = None


class SignalStrategyVersionRead(BaseModel):
    id: int
    strategy_id: int
    version: int
    inputs: List[SignalStrategyInputDef] = Field(default_factory=list)
    variables: List[AlertVariableDef] = Field(default_factory=list)
    outputs: List[SignalStrategyOutputDef] = Field(default_factory=list)
    compatibility: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    created_at: datetime

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover

        class Config:
            orm_mode = True


class SignalStrategyRead(BaseModel):
    id: int
    scope: SignalStrategyScope
    owner_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    regimes: List[SignalStrategyRegime] = Field(default_factory=list)
    latest_version: int
    created_at: datetime
    updated_at: datetime
    latest: Optional[SignalStrategyVersionRead] = None

    # Usage stats (optional)
    used_by_alerts: int = 0
    used_by_screeners: int = 0

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover

        class Config:
            orm_mode = True


class SignalStrategyExport(BaseModel):
    format: str = "sigma.signal_strategy.v1"
    name: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    regimes: List[str] = Field(default_factory=list)
    scope: str = "USER"
    versions: List[Dict[str, Any]] = Field(default_factory=list)


class SignalStrategyImportRequest(BaseModel):
    payload: Dict[str, Any]
    replace_existing: bool = False


class SignalStrategyApplyParams(BaseModel):
    output_name: str = Field(..., min_length=1)
    params: Dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "SignalStrategyCreate",
    "SignalStrategyUpdate",
    "SignalStrategyRead",
    "SignalStrategyVersionCreate",
    "SignalStrategyVersionRead",
    "SignalStrategyExport",
    "SignalStrategyImportRequest",
    "SignalStrategyApplyParams",
]
