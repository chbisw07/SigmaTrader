from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class KiteMcpStatusResponse(BaseModel):
    server_url: Optional[str] = None
    connected: bool = False
    authorized: bool = False
    server_info: Dict[str, Any] = Field(default_factory=dict)
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    last_error: Optional[str] = None


class KiteMcpAuthStartResponse(BaseModel):
    warning_text: str
    login_url: str


class KiteMcpToolsListResponse(BaseModel):
    tools: List[Dict[str, Any]] = Field(default_factory=list)


class KiteMcpToolCallRequest(BaseModel):
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class KiteMcpToolCallResponse(BaseModel):
    result: Dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "KiteMcpAuthStartResponse",
    "KiteMcpStatusResponse",
    "KiteMcpToolCallRequest",
    "KiteMcpToolCallResponse",
    "KiteMcpToolsListResponse",
]
