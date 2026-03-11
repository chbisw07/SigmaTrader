from __future__ import annotations

import json
from typing import Any, Literal
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.crypto import decrypt_token, encrypt_token
from app.models import BrokerSecret
from app.schemas.mcp_servers import McpSettings, McpTransport

MCP_SETTINGS_BROKER_NAME = "mcp"
MCP_SETTINGS_KEY = "mcp_settings_v1"

McpSettingsSource = Literal["db", "env_default", "db_invalid"]


def _json_loads(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw) if raw else {}
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_server_url(url: str | None) -> str | None:
    if url is None:
        return None
    u = str(url).strip()
    if not u:
        return None
    p = urlparse(u)
    if p.scheme not in {"http", "https"} or not p.netloc:
        raise ValueError("url must be a valid http(s) URL.")
    return u.rstrip("/")


def _env_defaults() -> McpSettings:
    # Non-Kite servers are opt-in and disabled by default.
    return McpSettings(
        servers={
            "tavily": {
                "label": "Tavily MCP (placeholder)",
                "enabled": False,
                "transport": McpTransport.sse,
                "url": None,
                "ai_enabled": False,
                "auth_method": "none",
                "auth_profile_ref": None,
            }
        }
    )


def get_mcp_settings_with_source(
    db: Session,
    settings: Settings,
) -> tuple[McpSettings, McpSettingsSource]:
    env_defaults = _env_defaults()
    row = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == MCP_SETTINGS_BROKER_NAME,
            BrokerSecret.key == MCP_SETTINGS_KEY,
            BrokerSecret.user_id.is_(None),
        )
        .one_or_none()
    )
    if row is None:
        return env_defaults, "env_default"
    try:
        raw = decrypt_token(settings, row.value_encrypted)
        parsed = _json_loads(raw)
        merged = {**env_defaults.model_dump(mode="json"), **parsed}
        return McpSettings.model_validate(merged), "db"
    except Exception:
        return env_defaults, "db_invalid"


def set_mcp_settings(
    db: Session,
    settings: Settings,
    config: McpSettings,
) -> BrokerSecret:
    payload = json.dumps(config.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    encrypted = encrypt_token(settings, payload)
    row = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == MCP_SETTINGS_BROKER_NAME,
            BrokerSecret.key == MCP_SETTINGS_KEY,
            BrokerSecret.user_id.is_(None),
        )
        .one_or_none()
    )
    if row is None:
        row = BrokerSecret(
            user_id=None,
            broker_name=MCP_SETTINGS_BROKER_NAME,
            key=MCP_SETTINGS_KEY,
            value_encrypted=encrypted,
        )
        db.add(row)
    else:
        row.value_encrypted = encrypted
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def normalize_mcp_settings(config: McpSettings) -> McpSettings:
    # Normalize URLs for SSE servers.
    for _sid, s in (config.servers or {}).items():
        if s.transport == McpTransport.sse:
            s.url = _normalize_server_url(s.url)
    return config


__all__ = [
    "MCP_SETTINGS_BROKER_NAME",
    "MCP_SETTINGS_KEY",
    "McpSettingsSource",
    "get_mcp_settings_with_source",
    "normalize_mcp_settings",
    "set_mcp_settings",
]
