from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.crypto import decrypt_token, encrypt_token
from app.models import BrokerSecret


def get_broker_secret(
    db: Session,
    settings: Settings,  # noqa: ARG001 - kept for future extensions/logging
    broker_name: str,
    key: str,
) -> Optional[str]:
    """Return a decrypted secret value for a broker/key, if present.

    This now **only** reads from the broker_secrets table; kite_config.json
    is no longer consulted so that all broker credentials are managed via
    the new encrypted storage and Settings UI.
    """

    secret = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == broker_name,
            BrokerSecret.key == key,
        )
        .one_or_none()
    )

    if secret is not None:
        return decrypt_token(settings, secret.value_encrypted)

    return None


def set_broker_secret(
    db: Session,
    settings: Settings,
    broker_name: str,
    key: str,
    value: str,
) -> BrokerSecret:
    """Encrypt and upsert a broker secret."""

    encrypted = encrypt_token(settings, value)

    secret = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == broker_name,
            BrokerSecret.key == key,
        )
        .one_or_none()
    )
    if secret is None:
        secret = BrokerSecret(
            broker_name=broker_name,
            key=key,
            value_encrypted=encrypted,
        )
        db.add(secret)
    else:
        secret.value_encrypted = encrypted

    db.commit()
    db.refresh(secret)
    return secret


def list_broker_secrets(
    db: Session,
    settings: Settings,
    broker_name: str,
) -> List[dict[str, str]]:
    """Return all decrypted secrets for a broker as key/value pairs."""

    secrets: List[BrokerSecret] = (
        db.query(BrokerSecret)
        .filter(BrokerSecret.broker_name == broker_name)
        .order_by(BrokerSecret.key)
        .all()
    )
    result: List[dict[str, str]] = []
    for s in secrets:
        value = decrypt_token(settings, s.value_encrypted)
        result.append({"key": s.key, "value": value})
    return result


def delete_broker_secret(
    db: Session,
    broker_name: str,
    key: str,
) -> bool:
    """Delete a broker secret if it exists.

    Returns True when a row was deleted, False if nothing matched.
    """

    secret = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == broker_name,
            BrokerSecret.key == key,
        )
        .one_or_none()
    )
    if secret is None:
        return False

    db.delete(secret)
    db.commit()
    return True


__all__ = [
    "get_broker_secret",
    "set_broker_secret",
    "list_broker_secrets",
    "delete_broker_secret",
]
