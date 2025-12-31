from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.crypto import decrypt_token
from app.db.session import get_db
from app.models import BrokerSecret
from app.services.webhook_secrets import (
    TRADINGVIEW_WEBHOOK_SECRET_KEY,
    WEBHOOK_BROKER_NAME,
    get_tradingview_webhook_secret,
    set_tradingview_webhook_secret,
)

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


class TradingViewWebhookSecretRead(BaseModel):
    value: str | None
    source: str  # db|env|unset


class TradingViewWebhookSecretUpdate(BaseModel):
    value: str


@router.get(
    "/tradingview-secret",
    response_model=TradingViewWebhookSecretRead,
)
def read_tradingview_webhook_secret(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TradingViewWebhookSecretRead:
    db_row = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == WEBHOOK_BROKER_NAME,
            BrokerSecret.key == TRADINGVIEW_WEBHOOK_SECRET_KEY,
            BrokerSecret.user_id.is_(None),
        )
        .one_or_none()
    )

    if db_row is not None:
        return TradingViewWebhookSecretRead(
            value=decrypt_token(settings, db_row.value_encrypted),
            source="db",
        )
    if settings.tradingview_webhook_secret:
        return TradingViewWebhookSecretRead(
            value=settings.tradingview_webhook_secret,
            source="env",
        )
    return TradingViewWebhookSecretRead(value=None, source="unset")


@router.put(
    "/tradingview-secret",
    response_model=TradingViewWebhookSecretRead,
)
def update_tradingview_webhook_secret(
    payload: TradingViewWebhookSecretUpdate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TradingViewWebhookSecretRead:
    set_tradingview_webhook_secret(db, settings, payload.value)
    value = get_tradingview_webhook_secret(db, settings)
    if (payload.value or "").strip():
        source = "db"
    elif settings.tradingview_webhook_secret:
        source = "env"
    else:
        source = "unset"
    return TradingViewWebhookSecretRead(value=value, source=source)


__all__ = ["router"]
