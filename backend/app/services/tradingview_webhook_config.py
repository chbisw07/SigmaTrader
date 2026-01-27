from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.crypto import decrypt_token, encrypt_token
from app.models import BrokerSecret
from app.services.webhook_secrets import WEBHOOK_BROKER_NAME

TRADINGVIEW_WEBHOOK_CONFIG_KEY = "tradingview_webhook_config"


@dataclass(frozen=True)
class TradingViewWebhookConfig:
    mode: str = "MANUAL"  # MANUAL|AUTO
    broker_name: str = "zerodha"
    execution_target: str = "LIVE"  # LIVE|PAPER
    default_product: str = "CNC"  # CNC|MIS (used when payload omits product)
    fallback_to_waiting_on_error: bool = True

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "TradingViewWebhookConfig":
        raw = raw or {}
        mode = str(raw.get("mode") or "MANUAL").strip().upper()
        if mode not in {"MANUAL", "AUTO"}:
            mode = "MANUAL"

        broker_name = str(raw.get("broker_name") or "zerodha").strip().lower()
        if not broker_name:
            broker_name = "zerodha"

        execution_target = str(raw.get("execution_target") or "LIVE").strip().upper()
        if execution_target not in {"LIVE", "PAPER"}:
            execution_target = "LIVE"

        default_product = str(raw.get("default_product") or "CNC").strip().upper()
        if default_product not in {"CNC", "MIS"}:
            default_product = "CNC"

        fallback = raw.get("fallback_to_waiting_on_error")
        if isinstance(fallback, bool):
            fallback_to_waiting = fallback
        else:
            fallback_to_waiting = True

        return cls(
            mode=mode,
            broker_name=broker_name,
            execution_target=execution_target,
            default_product=default_product,
            fallback_to_waiting_on_error=fallback_to_waiting,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "broker_name": self.broker_name,
            "execution_target": self.execution_target,
            "default_product": self.default_product,
            "fallback_to_waiting_on_error": bool(self.fallback_to_waiting_on_error),
        }


def _load_config_row(
    db: Session,
    *,
    user_id: int | None,
) -> BrokerSecret | None:
    return (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == WEBHOOK_BROKER_NAME,
            BrokerSecret.key == TRADINGVIEW_WEBHOOK_CONFIG_KEY,
            (
                (BrokerSecret.user_id == user_id)
                if user_id is not None
                else BrokerSecret.user_id.is_(None)
            ),
        )
        .one_or_none()
    )


def get_tradingview_webhook_config_with_source(
    db: Session,
    settings: Settings,
    *,
    user_id: int | None = None,
) -> tuple[TradingViewWebhookConfig, str]:
    """Return (config, source) for TradingView webhook routing settings.

    source is one of: db_user | db_global | default
    """

    row = _load_config_row(db, user_id=user_id) if user_id is not None else None
    if row is not None:
        source = "db_user"
    else:
        row = _load_config_row(db, user_id=None)
        source = "db_global" if row is not None else "default"

    if row is None:
        return TradingViewWebhookConfig(), source

    try:
        raw = decrypt_token(settings, row.value_encrypted)
        parsed = json.loads(raw) if raw else {}
    except Exception:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    return TradingViewWebhookConfig.from_dict(parsed), source


def get_tradingview_webhook_config(
    db: Session,
    settings: Settings,
    *,
    user_id: int | None = None,
) -> TradingViewWebhookConfig:
    """Return TradingView webhook routing settings.

    Precedence:
    1) User-scoped config (user_id)
    2) Global config (user_id IS NULL)
    3) Defaults
    """

    cfg, _source = get_tradingview_webhook_config_with_source(
        db, settings, user_id=user_id
    )
    return cfg


def set_tradingview_webhook_config(
    db: Session,
    settings: Settings,
    config: TradingViewWebhookConfig,
    *,
    user_id: int | None = None,
) -> TradingViewWebhookConfig:
    """Upsert TradingView webhook routing settings (global by default)."""

    payload = json.dumps(config.to_dict(), ensure_ascii=False)
    encrypted = encrypt_token(settings, payload)

    row = _load_config_row(db, user_id=user_id)
    if row is None:
        row = BrokerSecret(
            user_id=user_id,
            broker_name=WEBHOOK_BROKER_NAME,
            key=TRADINGVIEW_WEBHOOK_CONFIG_KEY,
            value_encrypted=encrypted,
        )
        db.add(row)
    else:
        row.value_encrypted = encrypted

    db.commit()
    return config


__all__ = [
    "TRADINGVIEW_WEBHOOK_CONFIG_KEY",
    "TradingViewWebhookConfig",
    "get_tradingview_webhook_config",
    "get_tradingview_webhook_config_with_source",
    "set_tradingview_webhook_config",
]
