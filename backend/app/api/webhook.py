from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.market_hours import is_market_open_now
from app.db.session import get_db
from app.models import Alert, Strategy, User
from app.schemas.webhook import TradingViewWebhookPayload
from app.services import create_order_from_alert
from app.services.paper_trading import submit_paper_order
from app.services.system_events import record_system_event
from app.services.tradingview_zerodha_adapter import (
    NormalizedAlert,
    normalize_tradingview_payload_for_zerodha,
)

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

    # Route alert to a specific SigmaTrader user. For multi-user safety we
    # require TradingView payloads to carry an explicit st_user_id that
    # matches an existing username; otherwise we ignore the alert.
    st_user = (payload.st_user_id or "").strip()
    if not st_user:
        logger.info(
            "Ignoring webhook without st_user_id",
            extra={
                "extra": {
                    "correlation_id": correlation_id,
                    "strategy": payload.strategy_name,
                    "platform": payload.platform,
                }
            },
        )
        record_system_event(
            db,
            level="INFO",
            category="alert",
            message="Alert ignored: missing st_user_id",
            correlation_id=correlation_id,
            details={
                "strategy": payload.strategy_name,
                "platform": payload.platform,
            },
        )
        return {"status": "ignored", "reason": "missing_st_user_id"}

    user: User | None = db.query(User).filter(User.username == st_user).one_or_none()
    if user is None:
        logger.warning(
            "Ignoring webhook for unknown st_user_id",
            extra={
                "extra": {
                    "correlation_id": correlation_id,
                    "strategy": payload.strategy_name,
                    "platform": payload.platform,
                    "st_user_id": st_user,
                }
            },
        )
        record_system_event(
            db,
            level="WARNING",
            category="alert",
            message="Alert ignored: unknown st_user_id",
            correlation_id=correlation_id,
            details={
                "strategy": payload.strategy_name,
                "platform": payload.platform,
                "st_user_id": st_user,
            },
        )
        return {
            "status": "ignored",
            "reason": "unknown_st_user_id",
            "st_user_id": st_user,
        }

    strategy: Strategy | None = (
        db.query(Strategy).filter(Strategy.name == payload.strategy_name).one_or_none()
    )

    normalized: NormalizedAlert = normalize_tradingview_payload_for_zerodha(
        payload=payload,
        user=user,
    )

    alert = Alert(
        user_id=normalized.user_id,
        strategy_id=strategy.id if strategy else None,
        symbol=normalized.symbol_display,
        exchange=normalized.broker_exchange,
        interval=normalized.timeframe,
        action=normalized.side,
        qty=normalized.qty,
        price=normalized.price,
        platform=payload.platform,
        raw_payload=normalized.raw_payload,
        bar_time=normalized.bar_time,
        reason=normalized.reason,
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
        product=normalized.product,
        order_type=normalized.order_type,
        user_id=alert.user_id,
    )

    # For AUTO strategies we immediately execute the order via the same
    # execution path used by the manual queue endpoint. When the
    # strategy is configured for PAPER execution we instead submit the
    # order to the paper engine and skip contacting Zerodha. Paper
    # execution respects market hours to avoid filling on stale prices.
    if auto_execute:
        try:
            exec_target = "LIVE"
            if strategy is not None:
                exec_target = getattr(strategy, "execution_target", "LIVE")

            if exec_target == "PAPER":
                if not is_market_open_now():
                    order.simulated = True
                    order.status = "FAILED"
                    order.error_message = "Paper AUTO order rejected: market is closed."
                    db.add(order)
                    db.commit()
                    db.refresh(order)
                    record_system_event(
                        db,
                        level="WARNING",
                        category="paper",
                        message="AUTO paper order rejected: market closed",
                        correlation_id=correlation_id,
                        details={
                            "order_id": order.id,
                            "symbol": order.symbol,
                            "strategy": payload.strategy_name,
                        },
                    )
                else:
                    submit_paper_order(
                        db,
                        settings,
                        order,
                        correlation_id=correlation_id,
                    )
            else:
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
