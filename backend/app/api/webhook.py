from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import Alert, Strategy
from app.schemas.webhook import TradingViewWebhookPayload
from app.services import create_order_from_alert
from app.services.system_events import record_system_event

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
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """Ingest a TradingView webhook alert and persist it as an Alert row.

    The `secret` field must match the configured `tradingview_webhook_secret`
    when one is set; otherwise a 401 response is returned.
    """

    correlation_id = getattr(request.state, "correlation_id", None)

    expected_secret = settings.tradingview_webhook_secret
    if expected_secret and payload.secret != expected_secret:
        logger.warning(
            "Received webhook with invalid secret",
            extra={
                "extra": {
                    "correlation_id": correlation_id,
                    "strategy": payload.strategy_name,
                    "platform": payload.platform,
                }
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret.",
        )

    # For now we only process alerts targeting Zerodha / generic TradingView.
    platform_normalized = (payload.platform or "").lower()
    if platform_normalized and platform_normalized not in {"zerodha", "tradingview"}:
        logger.info(
            "Ignoring webhook for unsupported platform",
            extra={
                "extra": {
                    "correlation_id": correlation_id,
                    "strategy": payload.strategy_name,
                    "platform": payload.platform,
                }
            },
        )
        return {"status": "ignored", "platform": payload.platform}

    strategy: Strategy | None = (
        db.query(Strategy).filter(Strategy.name == payload.strategy_name).one_or_none()
    )

    product = (payload.trade_details.product or "MIS").upper()
    order_type = "MARKET"

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

    # Determine execution mode routing based on strategy configuration.
    mode = "MANUAL"
    auto_execute = False
    if strategy is not None and strategy.enabled:
        if strategy.execution_mode == "AUTO":
            mode = "AUTO"
            auto_execute = True

    order = create_order_from_alert(
        db=db,
        alert=alert,
        mode=mode,
        product=product,
        order_type=order_type,
    )

    # For AUTO strategies we immediately execute the order via the same
    # execution path used by the manual queue endpoint. Risk checks and
    # more advanced routing will be layered in S06/G02+.
    if auto_execute:
        try:
            from app.api.orders import execute_order as execute_order_api

            execute_order_api(
                order_id=order.id,
                request=request,
                db=db,
                settings=settings,
            )
        except HTTPException as exc:
            # The execute_order handler will have updated order status /
            # error_message appropriately. When Zerodha is not connected
            # we ensure the order records a clear failure reason so the
            # manual queue and history views reflect what happened.
            if exc.status_code == status.HTTP_400_BAD_REQUEST and isinstance(
                exc.detail,
                str,
            ):
                if "Zerodha is not connected" in exc.detail:
                    order.status = "FAILED"
                    order.error_message = "Zerodha is not connected for AUTO mode."
                    db.add(order)
                    db.commit()
                    db.refresh(order)
                    record_system_event(
                        db,
                        level="WARNING",
                        category="order",
                        message="AUTO order rejected: broker not connected",
                        correlation_id=correlation_id,
                        details={
                            "order_id": order.id,
                            "symbol": order.symbol,
                            "strategy": payload.strategy_name,
                        },
                    )
            logger.exception(
                "AUTO execution failed for alert id=%s order id=%s strategy=%s",
                alert.id,
                order.id,
                payload.strategy_name,
            )
            raise

    logger.info(
        "Stored alert and created order",
        extra={
            "extra": {
                "correlation_id": correlation_id,
                "alert_id": alert.id,
                "order_id": order.id,
                "symbol": alert.symbol,
                "action": alert.action,
                "strategy": payload.strategy_name,
                "mode": mode,
            }
        },
    )

    # Persist a structured system event for observability.
    record_system_event(
        db,
        level="INFO",
        category="alert",
        message="Alert ingested and order created",
        correlation_id=correlation_id,
        details={
            "alert_id": alert.id,
            "order_id": order.id,
            "symbol": alert.symbol,
            "action": alert.action,
            "strategy": payload.strategy_name,
            "mode": mode,
        },
    )

    return {
        "id": alert.id,
        "alert_id": alert.id,
        "order_id": order.id,
        "status": "accepted",
    }


__all__ = ["router"]
