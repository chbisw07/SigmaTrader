from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ProviderDescriptor(BaseModel):
    id: str
    label: str
    kind: str  # remote|local
    requires_api_key: bool = False
    supports_base_url: bool = False
    default_base_url: Optional[str] = None
    supports_model_discovery: bool = True
    supports_test: bool = True


class AiProviderKeyRead(BaseModel):
    id: int
    provider: str
    key_name: str
    key_masked: str
    created_at: datetime
    updated_at: datetime


class AiProviderKeyCreate(BaseModel):
    provider: str
    key_name: str = Field(min_length=1, max_length=64)
    api_key_value: str = Field(min_length=1, max_length=4096)
    meta: Dict[str, Any] = Field(default_factory=dict)


class AiProviderKeyUpdate(BaseModel):
    key_name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    api_key_value: Optional[str] = Field(default=None, min_length=1, max_length=4096)
    meta: Optional[Dict[str, Any]] = None


class AiLimits(BaseModel):
    max_tokens_per_request: Optional[int] = Field(default=None, ge=1)
    max_cost_usd_per_request: Optional[float] = Field(default=None, ge=0)
    max_cost_usd_per_day: Optional[float] = Field(default=None, ge=0)


class AiActiveConfig(BaseModel):
    enabled: bool = False
    provider: str = "openai"
    model: Optional[str] = None
    base_url: Optional[str] = None
    active_key_id: Optional[int] = None
    do_not_send_pii: bool = True
    limits: AiLimits = Field(default_factory=AiLimits)

    # Optional denormalized key metadata for UI.
    active_key: Optional[AiProviderKeyRead] = None


class AiActiveConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    active_key_id: Optional[int] = None
    do_not_send_pii: Optional[bool] = None
    limits: Optional[AiLimits] = None


class DiscoverModelsRequest(BaseModel):
    provider: str
    base_url: Optional[str] = None
    key_id: Optional[int] = None


class ModelEntry(BaseModel):
    id: str
    label: str
    source: str = "discovered"  # discovered|curated
    raw: Dict[str, Any] = Field(default_factory=dict)


class DiscoverModelsResponse(BaseModel):
    models: List[ModelEntry] = Field(default_factory=list)


class AiTestRequest(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    key_id: Optional[int] = None
    prompt: str = Field(min_length=1, max_length=4000)


class AiUsage(BaseModel):
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class AiTestResponse(BaseModel):
    text: str
    latency_ms: int
    usage: AiUsage = Field(default_factory=AiUsage)
    raw_metadata: Dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "AiActiveConfig",
    "AiActiveConfigUpdate",
    "AiProviderKeyCreate",
    "AiProviderKeyRead",
    "AiProviderKeyUpdate",
    "AiTestRequest",
    "AiTestResponse",
    "DiscoverModelsRequest",
    "DiscoverModelsResponse",
    "ModelEntry",
    "ProviderDescriptor",
]

