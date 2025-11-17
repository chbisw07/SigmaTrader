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
    user_id: int | None = None,
) -> Optional[str]:
    """Return a decrypted secret value for a broker/key, if present.

    When ``user_id`` is provided secrets are scoped to that user; otherwise
    only secrets with ``user_id IS NULL`` are considered (legacy/global
    entries). This lets us gradually migrate from global to per-user
    broker configuration.
    """

    query = db.query(BrokerSecret).filter(
        BrokerSecret.broker_name == broker_name,
        BrokerSecret.key == key,
    )
    if user_id is not None:
        query = query.filter(BrokerSecret.user_id == user_id)
    else:
        query = query.filter(BrokerSecret.user_id.is_(None))

    secret = query.one_or_none()
    if secret is not None:
        return decrypt_token(settings, secret.value_encrypted)

    return None


def set_broker_secret(
    db: Session,
    settings: Settings,
    broker_name: str,
    key: str,
    value: str,
    user_id: int,
) -> BrokerSecret:
    """Encrypt and upsert a broker secret for a specific user."""

    encrypted = encrypt_token(settings, value)

    secret = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == broker_name,
            BrokerSecret.key == key,
            BrokerSecret.user_id == user_id,
        )
        .one_or_none()
    )
    if secret is None:
        secret = BrokerSecret(
            user_id=user_id,
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
    settings: Settings,  # noqa: ARG001
    broker_name: str,
    user_id: int,
) -> List[dict[str, str]]:
    """Return all decrypted secrets for a broker/user as key/value pairs."""

    secrets: List[BrokerSecret] = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == broker_name,
            BrokerSecret.user_id == user_id,
        )
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
    user_id: int,
) -> bool:
    """Delete a broker secret if it exists for the given user.

    Returns True when a row was deleted, False if nothing matched.
    """

    secret = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == broker_name,
            BrokerSecret.key == key,
            BrokerSecret.user_id == user_id,
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
