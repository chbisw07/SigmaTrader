from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import Alert, Strategy
from app.schemas.webhook import TradingViewWebhookPayload
from app.services import create_order_from_alert

# ruff: noqa: B008  # FastAPI dependency injection pattern

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/tradingview",
    status_code=status.HTTP_201_CREATED,
    summary="Receive TradingView webhook alerts",
)
def tradingview_webhook(
    payload: TradingViewWebhookPayload,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """Ingest a TradingView webhook alert and persist it as an Alert row.

    The `secret` field must match the configured `tradingview_webhook_secret`
    when one is set; otherwise a 401 response is returned.
    """

    expected_secret = settings.tradingview_webhook_secret
    if expected_secret and payload.secret != expected_secret:
        logger.warning(
            "Received webhook with invalid secret for strategy=%s",
            payload.strategy_name,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret.",
        )

    strategy: Strategy | None = (
        db.query(Strategy).filter(Strategy.name == payload.strategy_name).one_or_none()
    )

    alert = Alert(
        strategy_id=strategy.id if strategy else None,
        symbol=payload.symbol,
        exchange=payload.exchange,
        interval=payload.interval,
        action=payload.trade_details.order_action,
        qty=payload.trade_details.quantity,
        price=payload.trade_details.price,
        platform=payload.platform,
        raw_payload=payload.json(),
        bar_time=payload.bar_time,
    )

    db.add(alert)
    db.commit()
    db.refresh(alert)

    order = create_order_from_alert(db=db, alert=alert, mode="MANUAL")

    logger.info(
        "Stored alert id=%s symbol=%s action=%s strategy=%s",
        alert.id,
        alert.symbol,
        alert.action,
        payload.strategy_name,
    )

    return {
        "id": alert.id,
        "alert_id": alert.id,
        "order_id": order.id,
        "status": "accepted",
    }


__all__ = ["router"]
