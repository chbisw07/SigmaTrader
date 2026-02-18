from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.crypto import decrypt_token, encrypt_token
from app.models import BrokerSecret

KITE_MCP_BROKER_NAME = "kite_mcp"
AUTH_SESSION_KEY = "auth_session_id_v1"
REQUEST_TOKEN_KEY = "request_token_v1"


def get_auth_session_id(db: Session, settings: Settings) -> str | None:
    row = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == KITE_MCP_BROKER_NAME,
            BrokerSecret.key == AUTH_SESSION_KEY,
            BrokerSecret.user_id.is_(None),
        )
        .one_or_none()
    )
    if row is None:
        return None
    try:
        return decrypt_token(settings, row.value_encrypted)
    except Exception:
        return None


def set_auth_session_id(db: Session, settings: Settings, value: str) -> BrokerSecret:
    v = (value or "").strip()
    if not v:
        raise ValueError("auth_session_id is required.")
    encrypted = encrypt_token(settings, v)
    row = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == KITE_MCP_BROKER_NAME,
            BrokerSecret.key == AUTH_SESSION_KEY,
            BrokerSecret.user_id.is_(None),
        )
        .one_or_none()
    )
    if row is None:
        row = BrokerSecret(
            user_id=None,
            broker_name=KITE_MCP_BROKER_NAME,
            key=AUTH_SESSION_KEY,
            value_encrypted=encrypted,
        )
        db.add(row)
    else:
        row.value_encrypted = encrypted
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def clear_auth_session_id(db: Session) -> None:
    row = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == KITE_MCP_BROKER_NAME,
            BrokerSecret.key == AUTH_SESSION_KEY,
            BrokerSecret.user_id.is_(None),
        )
        .one_or_none()
    )
    if row is None:
        return
    db.delete(row)
    db.commit()


def get_request_token(db: Session, settings: Settings) -> str | None:
    row = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == KITE_MCP_BROKER_NAME,
            BrokerSecret.key == REQUEST_TOKEN_KEY,
            BrokerSecret.user_id.is_(None),
        )
        .one_or_none()
    )
    if row is None:
        return None
    try:
        return decrypt_token(settings, row.value_encrypted)
    except Exception:
        return None


def set_request_token(db: Session, settings: Settings, value: str) -> BrokerSecret:
    v = (value or "").strip()
    if not v:
        raise ValueError("request_token is required.")
    encrypted = encrypt_token(settings, v)
    row = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == KITE_MCP_BROKER_NAME,
            BrokerSecret.key == REQUEST_TOKEN_KEY,
            BrokerSecret.user_id.is_(None),
        )
        .one_or_none()
    )
    if row is None:
        row = BrokerSecret(
            user_id=None,
            broker_name=KITE_MCP_BROKER_NAME,
            key=REQUEST_TOKEN_KEY,
            value_encrypted=encrypted,
        )
        db.add(row)
    else:
        row.value_encrypted = encrypted
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def clear_request_token(db: Session) -> None:
    row = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == KITE_MCP_BROKER_NAME,
            BrokerSecret.key == REQUEST_TOKEN_KEY,
            BrokerSecret.user_id.is_(None),
        )
        .one_or_none()
    )
    if row is None:
        return
    db.delete(row)
    db.commit()


__all__ = [
    "AUTH_SESSION_KEY",
    "REQUEST_TOKEN_KEY",
    "KITE_MCP_BROKER_NAME",
    "clear_auth_session_id",
    "clear_request_token",
    "get_auth_session_id",
    "get_request_token",
    "set_auth_session_id",
    "set_request_token",
]
