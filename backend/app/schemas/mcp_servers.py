from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.ai_settings import KiteMcpStatus


class McpTransport(str, Enum):
    sse = "sse"
    stdio = "stdio"


class McpServerConfig(BaseModel):
    # Display metadata
    label: Optional[str] = None

    # Enabled == should SigmaTrader attempt to use this server.
    enabled: bool = False

    # Transport + config (future-proof; only SSE is actively used today).
    transport: McpTransport = McpTransport.sse
    url: Optional[str] = None
    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)

    # Auth is best-effort metadata for now; only Kite uses a live flow.
    auth_method: str = "none"
    auth_profile_ref: Optional[str] = None

    # Cached status (updated via explicit Test / Refresh actions).
    last_status: KiteMcpStatus = KiteMcpStatus.unknown
    last_checked_ts: Optional[datetime] = None
    last_error: Optional[str] = None
    capabilities_cache: Dict[str, Any] = Field(default_factory=dict)


class McpSettings(BaseModel):
    # Non-Kite MCP servers live here. Kite is managed via AI settings for
    # backwards compatibility.
    servers: Dict[str, McpServerConfig] = Field(default_factory=dict)


class McpServerCard(BaseModel):
    id: str
    label: str
    enabled: bool
    transport: str
    configured: bool
    status: KiteMcpStatus
    last_checked_ts: Optional[datetime] = None
    last_error: Optional[str] = None
    authorized: Optional[bool] = None
    tools_available_count: Optional[int] = None


class McpServersSummaryResponse(BaseModel):
    # Global toggles that currently live under AI settings.
    monitoring_enabled: bool = False
    servers: List[McpServerCard] = Field(default_factory=list)


class McpJsonConfigResponse(BaseModel):
    config: Dict[str, Any] = Field(default_factory=dict)


class McpJsonConfigUpdateRequest(BaseModel):
    config: Dict[str, Any] = Field(default_factory=dict)

class KiteMcpServerConfigResponse(BaseModel):
    enabled: bool = False
    monitoring_enabled: bool = False

    server_url: Optional[str] = None
    transport_mode: str = "remote"
    auth_method: str = "none"
    auth_profile_ref: Optional[str] = None
    scopes: Dict[str, bool] = Field(default_factory=dict)
    broker_adapter: str = "zerodha"

    last_status: KiteMcpStatus = KiteMcpStatus.unknown
    last_checked_ts: Optional[datetime] = None
    last_connected_ts: Optional[datetime] = None
    tools_available_count: Optional[int] = None
    last_error: Optional[str] = None
    capabilities_cache: Dict[str, Any] = Field(default_factory=dict)


class KiteMcpServerConfigUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    monitoring_enabled: Optional[bool] = None

    server_url: Optional[str] = None
    transport_mode: Optional[str] = None
    auth_method: Optional[str] = None
    auth_profile_ref: Optional[str] = None
    scopes: Optional[Dict[str, Optional[bool]]] = None
    broker_adapter: Optional[str] = None


class McpTool(BaseModel):
    name: str
    description: Optional[str] = None
    inputSchema: Optional[Dict[str, Any]] = None
    annotations: Optional[Dict[str, Any]] = None


class McpToolsListResponse(BaseModel):
    tools: List[Dict[str, Any]] = Field(default_factory=list)


class McpToolCallRequest(BaseModel):
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class McpToolCallResponse(BaseModel):
    result: Dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "McpJsonConfigResponse",
    "McpJsonConfigUpdateRequest",
    "McpServerCard",
    "McpServerConfig",
    "McpServersSummaryResponse",
    "McpSettings",
    "McpToolCallRequest",
    "McpToolCallResponse",
    "McpToolsListResponse",
    "McpTransport",
    "KiteMcpServerConfigResponse",
    "KiteMcpServerConfigUpdateRequest",
]
