from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.crypto import decrypt_token, encrypt_token
from app.models import BrokerSecret

TRADINGVIEW_WEBHOOK_SECRET_KEY = "tradingview_webhook_secret"
WEBHOOK_BROKER_NAME = "webhook"


def get_tradingview_webhook_secret(
    db: Session,
    settings: Settings,
) -> Optional[str]:
    """Return the TradingView webhook secret.

    Precedence:
    1) DB-stored secret (global; user_id IS NULL)
    2) Environment-based secret (ST_TRADINGVIEW_WEBHOOK_SECRET)
    """

    secret = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == WEBHOOK_BROKER_NAME,
            BrokerSecret.key == TRADINGVIEW_WEBHOOK_SECRET_KEY,
            BrokerSecret.user_id.is_(None),
        )
        .one_or_none()
    )
    if secret is not None:
        return decrypt_token(settings, secret.value_encrypted)

    return settings.tradingview_webhook_secret


def set_tradingview_webhook_secret(
    db: Session,
    settings: Settings,
    value: str,
) -> None:
    """Upsert the TradingView webhook secret (global; user_id IS NULL).

    Passing an empty string clears the stored secret (falls back to env).
    """

    normalized = (value or "").strip()
    secret = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == WEBHOOK_BROKER_NAME,
            BrokerSecret.key == TRADINGVIEW_WEBHOOK_SECRET_KEY,
            BrokerSecret.user_id.is_(None),
        )
        .one_or_none()
    )

    if not normalized:
        if secret is not None:
            db.delete(secret)
            db.commit()
        return

    encrypted = encrypt_token(settings, normalized)
    if secret is None:
        secret = BrokerSecret(
            user_id=None,
            broker_name=WEBHOOK_BROKER_NAME,
            key=TRADINGVIEW_WEBHOOK_SECRET_KEY,
            value_encrypted=encrypted,
        )
        db.add(secret)
    else:
        secret.value_encrypted = encrypted

    db.commit()


__all__ = [
    "TRADINGVIEW_WEBHOOK_SECRET_KEY",
    "WEBHOOK_BROKER_NAME",
    "get_tradingview_webhook_secret",
    "set_tradingview_webhook_secret",
]
