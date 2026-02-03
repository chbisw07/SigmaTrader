from __future__ import annotations

import json
from typing import Literal

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.crypto import decrypt_token, encrypt_token
from app.models import BrokerSecret

RISK_ENGINE_BROKER_NAME = "risk"
RISK_ENGINE_V2_FLAG_KEY = "risk_engine_v2_enabled"

RiskEngineV2FlagSource = Literal["db", "env_default", "db_invalid"]


def get_risk_engine_v2_enabled(
    db: Session, settings: Settings
) -> tuple[bool, RiskEngineV2FlagSource]:
    """Return (enabled, source).

    Backed by DB (BrokerSecret). If missing, defaults to False (safe).
    """

    row = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == RISK_ENGINE_BROKER_NAME,
            BrokerSecret.key == RISK_ENGINE_V2_FLAG_KEY,
            BrokerSecret.user_id.is_(None),
        )
        .one_or_none()
    )
    if row is None:
        return False, "env_default"

    try:
        raw = decrypt_token(settings, row.value_encrypted)
        parsed = json.loads(raw) if raw else {}
        if not isinstance(parsed, dict):
            parsed = {}
        enabled = bool(parsed.get("enabled", False))
        return enabled, "db"
    except Exception:
        # Fail closed: if DB row exists but is corrupted/unreadable, keep v2 OFF.
        return False, "db_invalid"


def set_risk_engine_v2_enabled(db: Session, settings: Settings, enabled: bool) -> BrokerSecret:
    payload = json.dumps({"enabled": bool(enabled)}, ensure_ascii=False)
    encrypted = encrypt_token(settings, payload)

    row = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == RISK_ENGINE_BROKER_NAME,
            BrokerSecret.key == RISK_ENGINE_V2_FLAG_KEY,
            BrokerSecret.user_id.is_(None),
        )
        .one_or_none()
    )
    if row is None:
        row = BrokerSecret(
            user_id=None,
            broker_name=RISK_ENGINE_BROKER_NAME,
            key=RISK_ENGINE_V2_FLAG_KEY,
            value_encrypted=encrypted,
        )
        db.add(row)
    else:
        row.value_encrypted = encrypted
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


__all__ = ["get_risk_engine_v2_enabled", "set_risk_engine_v2_enabled"]

