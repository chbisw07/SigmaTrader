from __future__ import annotations

import json
from typing import Any, Dict, Literal
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.crypto import decrypt_token, encrypt_token
from app.models import BrokerSecret
from app.schemas.ai_provider import AiActiveConfig, AiActiveConfigUpdate
from app.services.ai.provider_registry import get_provider
from app.services.ai.provider_keys import get_key
from app.pydantic_compat import model_to_dict

AI_PROVIDER_CONFIG_BROKER_NAME = "ai_provider"
AI_PROVIDER_CONFIG_KEY = "active_config_v1"

AiConfigSource = Literal["db", "default", "db_invalid"]


def _json_loads(raw: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(raw) if raw else {}
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_base_url(url: str | None) -> str | None:
    if url is None:
        return None
    u = str(url).strip()
    if not u:
        return None
    p = urlparse(u)
    if p.scheme not in {"http", "https"} or not p.netloc:
        raise ValueError("base_url must be a valid http(s) URL.")
    return u.rstrip("/")


def get_active_config(db: Session, settings: Settings) -> tuple[AiActiveConfig, AiConfigSource]:
    row = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == AI_PROVIDER_CONFIG_BROKER_NAME,
            BrokerSecret.key == AI_PROVIDER_CONFIG_KEY,
            BrokerSecret.user_id.is_(None),
        )
        .one_or_none()
    )
    if row is None:
        return AiActiveConfig(), "default"
    try:
        raw = decrypt_token(settings, row.value_encrypted)
        parsed = _json_loads(raw)
        return AiActiveConfig.model_validate(parsed), "db"
    except Exception:
        return AiActiveConfig(), "db_invalid"


def set_active_config(db: Session, settings: Settings, cfg: AiActiveConfig) -> BrokerSecret:
    payload = json.dumps(cfg.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    encrypted = encrypt_token(settings, payload)
    row = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == AI_PROVIDER_CONFIG_BROKER_NAME,
            BrokerSecret.key == AI_PROVIDER_CONFIG_KEY,
            BrokerSecret.user_id.is_(None),
        )
        .one_or_none()
    )
    if row is None:
        row = BrokerSecret(
            user_id=None,
            broker_name=AI_PROVIDER_CONFIG_BROKER_NAME,
            key=AI_PROVIDER_CONFIG_KEY,
            value_encrypted=encrypted,
        )
        db.add(row)
    else:
        row.value_encrypted = encrypted
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def apply_config_update(
    db: Session,
    settings: Settings,
    *,
    existing: AiActiveConfig,
    update: AiActiveConfigUpdate,
) -> AiActiveConfig:
    base = existing.model_dump(mode="json")
    patch = model_to_dict(update)

    merged = {**base, **{k: v for k, v in patch.items() if v is not None}}
    if isinstance(patch.get("limits"), dict) and isinstance(base.get("limits"), dict):
        merged["limits"] = {**base["limits"], **{k: v for k, v in patch["limits"].items() if v is not None}}

    provider_id = str(merged.get("provider") or "").strip().lower()
    info = get_provider(provider_id)
    if info is None or info.supports_test is False and provider_id != "anthropic":
        # Unknown provider is rejected. "anthropic" allowed but not testable.
        raise ValueError("Unsupported provider.")
    merged["provider"] = provider_id

    # Normalize base_url if present.
    if "base_url" in merged:
        merged["base_url"] = _normalize_base_url(merged.get("base_url"))

    cfg = AiActiveConfig.model_validate(merged)

    # Enforce base_url presence for providers that require it.
    if info.supports_base_url:
        cfg.base_url = cfg.base_url or info.default_base_url
        cfg.base_url = _normalize_base_url(cfg.base_url) if cfg.base_url else None
        if not cfg.base_url:
            raise ValueError("base_url is required for this provider.")
    else:
        cfg.base_url = None

    # Ensure active_key_id belongs to provider when set.
    if cfg.active_key_id is not None:
        row = get_key(db, key_id=int(cfg.active_key_id), user_id=None)
        if row is None or row.provider != provider_id:
            cfg.active_key_id = None

    return cfg


__all__ = [
    "AI_PROVIDER_CONFIG_BROKER_NAME",
    "AI_PROVIDER_CONFIG_KEY",
    "AiConfigSource",
    "apply_config_update",
    "get_active_config",
    "set_active_config",
]
