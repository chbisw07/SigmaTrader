from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.crypto import decrypt_token, encrypt_token
from app.models import BrokerSecret
from app.schemas.risk_policy import RiskPolicy

RISK_POLICY_BROKER_NAME = "risk"
RISK_POLICY_KEY = "risk_policy_v1"


def default_risk_policy() -> RiskPolicy:
    return RiskPolicy()


def get_risk_policy(db: Session, settings: Settings) -> tuple[RiskPolicy, str]:
    """Return (policy, source) where source is db|default."""

    row = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == RISK_POLICY_BROKER_NAME,
            BrokerSecret.key == RISK_POLICY_KEY,
            BrokerSecret.user_id.is_(None),
        )
        .one_or_none()
    )
    if row is None:
        return default_risk_policy(), "default"
    try:
        raw = decrypt_token(settings, row.value_encrypted)
        parsed = json.loads(raw) if raw else {}
    except Exception:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    try:
        return RiskPolicy(**parsed), "db"
    except Exception:
        return default_risk_policy(), "default"


def set_risk_policy(db: Session, settings: Settings, policy: RiskPolicy) -> RiskPolicy:
    payload = json.dumps(policy.to_dict(), ensure_ascii=False)
    encrypted = encrypt_token(settings, payload)

    row = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == RISK_POLICY_BROKER_NAME,
            BrokerSecret.key == RISK_POLICY_KEY,
            BrokerSecret.user_id.is_(None),
        )
        .one_or_none()
    )
    if row is None:
        row = BrokerSecret(
            user_id=None,
            broker_name=RISK_POLICY_BROKER_NAME,
            key=RISK_POLICY_KEY,
            value_encrypted=encrypted,
        )
        db.add(row)
    else:
        row.value_encrypted = encrypted
    db.commit()
    return policy


def reset_risk_policy(db: Session, settings: Settings) -> RiskPolicy:
    policy = default_risk_policy()
    return set_risk_policy(db, settings, policy)


__all__ = [
    "RISK_POLICY_BROKER_NAME",
    "RISK_POLICY_KEY",
    "default_risk_policy",
    "get_risk_policy",
    "set_risk_policy",
    "reset_risk_policy",
]
