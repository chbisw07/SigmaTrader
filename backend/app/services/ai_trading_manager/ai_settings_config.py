from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal, Optional
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.crypto import decrypt_token, encrypt_token
from app.models import BrokerSecret
from app.schemas.ai_settings import (
    AiSettings,
    AiSettingsUpdate,
    KiteMcpStatus,
)
from app.pydantic_compat import model_to_dict

AI_SETTINGS_BROKER_NAME = "ai_trading_manager"
AI_SETTINGS_KEY = "ai_settings_v1"

AiSettingsSource = Literal["db", "env_default", "db_invalid"]


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
        raise ValueError("server_url must be a valid http(s) URL.")
    return u.rstrip("/")


def _env_defaults(settings: Settings) -> AiSettings:
    # Defaults come from environment-backed Settings for backwards
    # compatibility, but the canonical runtime config lives in DB.
    return AiSettings(
        feature_flags={
            "ai_assistant_enabled": bool(getattr(settings, "ai_assistant_enabled", False)),
            "ai_execution_enabled": bool(getattr(settings, "ai_execution_enabled", False)),
            "kite_mcp_enabled": bool(getattr(settings, "kite_mcp_enabled", False)),
            "monitoring_enabled": bool(getattr(settings, "monitoring_enabled", False)),
        },
        kill_switch={
            "ai_execution_kill_switch": bool(getattr(settings, "ai_execution_kill_switch", False)),
            "execution_disabled_until_ts": None,
        },
        kite_mcp={
            "server_url": None,
            "transport_mode": "remote",
            "auth_method": "none",
            "auth_profile_ref": None,
            "scopes": {"read_only": True, "trade": False},
            "broker_adapter": str(getattr(settings, "ai_broker_name", "zerodha") or "zerodha").strip().lower(),
            "last_status": KiteMcpStatus.unknown,
            "last_checked_ts": None,
            "last_connected_ts": None,
            "tools_available_count": None,
            "last_error": None,
            "capabilities_cache": {},
        },
        llm_provider={
            "enabled": False,
            "provider": "stub",
            "model": None,
            "do_not_send_pii": True,
            "limits": {},
        },
    )


def get_ai_settings_with_source(
    db: Session,
    settings: Settings,
) -> tuple[AiSettings, AiSettingsSource]:
    env_defaults = _env_defaults(settings)
    row = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == AI_SETTINGS_BROKER_NAME,
            BrokerSecret.key == AI_SETTINGS_KEY,
            BrokerSecret.user_id.is_(None),
        )
        .one_or_none()
    )
    if row is None:
        return env_defaults, "env_default"
    try:
        raw = decrypt_token(settings, row.value_encrypted)
        parsed = _json_loads(raw)
        # Merge into env defaults (DB wins).
        merged = {**env_defaults.model_dump(mode="json"), **parsed}
        return AiSettings.model_validate(merged), "db"
    except Exception:
        # Fail closed: keep assistant off if config is corrupted.
        return AiSettings(), "db_invalid"


def set_ai_settings(
    db: Session,
    settings: Settings,
    config: AiSettings,
) -> BrokerSecret:
    payload = json.dumps(config.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    encrypted = encrypt_token(settings, payload)
    row = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == AI_SETTINGS_BROKER_NAME,
            BrokerSecret.key == AI_SETTINGS_KEY,
            BrokerSecret.user_id.is_(None),
        )
        .one_or_none()
    )
    if row is None:
        row = BrokerSecret(
            user_id=None,
            broker_name=AI_SETTINGS_BROKER_NAME,
            key=AI_SETTINGS_KEY,
            value_encrypted=encrypted,
        )
        db.add(row)
    else:
        row.value_encrypted = encrypted
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def apply_ai_settings_update(
    *,
    existing: AiSettings,
    update: AiSettingsUpdate,
) -> AiSettings:
    base = existing.model_dump(mode="json")
    patch = model_to_dict(update)

    def _merge_dict(dst: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
        for k, v in src.items():
            if v is None:
                continue
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                dst[k] = _merge_dict(dict(dst[k]), v)
            else:
                dst[k] = v
        return dst

    merged = _merge_dict(base, patch)

    # Normalize server URL (validate if provided).
    kite = merged.get("kite_mcp") if isinstance(merged.get("kite_mcp"), dict) else {}
    if isinstance(kite, dict) and "server_url" in kite:
        kite["server_url"] = _normalize_server_url(kite.get("server_url"))
        merged["kite_mcp"] = kite

    # Ensure last_checked_ts is always UTC-ish if present.
    if isinstance(kite, dict) and kite.get("last_checked_ts") and isinstance(kite["last_checked_ts"], str):
        try:
            # Keep string, pydantic will parse; no change needed.
            pass
        except Exception:
            kite["last_checked_ts"] = None

    cfg = AiSettings.model_validate(merged)

    # Ensure kill switch "until" is consistent.
    if cfg.kill_switch.execution_disabled_until_ts is not None:
        if cfg.kill_switch.execution_disabled_until_ts.tzinfo is None:
            cfg.kill_switch.execution_disabled_until_ts = cfg.kill_switch.execution_disabled_until_ts.replace(
                tzinfo=UTC
            )
        if cfg.kill_switch.execution_disabled_until_ts <= datetime.now(UTC):
            cfg.kill_switch.execution_disabled_until_ts = None

    return cfg


def is_execution_hard_disabled(config: AiSettings) -> bool:
    if config.kill_switch.ai_execution_kill_switch:
        return True
    until = config.kill_switch.execution_disabled_until_ts
    if until is not None and until > datetime.now(UTC):
        return True
    return False


def should_allow_execution_enable(config: AiSettings) -> tuple[bool, Optional[str]]:
    flags = config.feature_flags
    kite = config.kite_mcp
    if not flags.kite_mcp_enabled:
        return False, "Execution requires broker-truth (enable Kite MCP first)."
    if not kite.server_url:
        return False, "Kite MCP server URL is required before enabling execution."
    if kite.last_status != KiteMcpStatus.connected:
        return False, "Kite MCP must be connected (run Test Connection) before enabling execution."
    return True, None


__all__ = [
    "AI_SETTINGS_BROKER_NAME",
    "AI_SETTINGS_KEY",
    "AiSettingsSource",
    "apply_ai_settings_update",
    "get_ai_settings_with_source",
    "is_execution_hard_disabled",
    "set_ai_settings",
    "should_allow_execution_enable",
]
