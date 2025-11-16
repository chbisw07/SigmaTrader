from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.clients import ZerodhaClient
from app.config_files import load_kite_config
from app.core.config import Settings, get_settings
from app.core.crypto import decrypt_token
from app.db.session import get_db
from app.models import BrokerConnection, Order
from app.schemas.orders import OrderRead, OrderStatusUpdate, OrderUpdate
from app.services.risk import evaluate_order_risk
from app.services.system_events import record_system_event

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_zerodha_client(db: Session, settings: Settings) -> ZerodhaClient:
    """Construct a ZerodhaClient from stored broker connection.

    This function is defined separately to make it easy to monkeypatch in tests.
    """

    conn = (
        db.query(BrokerConnection)
        .filter(BrokerConnection.broker_name == "zerodha")
        .one_or_none()
    )
    if conn is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zerodha is not connected.",
        )

    kite_cfg = load_kite_config()
    access_token = decrypt_token(settings, conn.access_token_encrypted)

    # Import lazily to keep tests independent of the real library.
    from kiteconnect import KiteConnect  # type: ignore[import]

    kite = KiteConnect(api_key=kite_cfg.kite_connect.api_key)
    kite.set_access_token(access_token)

    return ZerodhaClient(kite)


@router.get("/", response_model=List[OrderRead])
def list_orders(
    status: Optional[str] = Query(None),
    strategy_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
) -> List[Order]:
    """Return a simple order history list with basic filters."""

    query = db.query(Order)
    if status is not None:
        query = query.filter(Order.status == status)
    if strategy_id is not None:
        query = query.filter(Order.strategy_id == strategy_id)
    return query.order_by(Order.created_at.desc()).all()


@router.get("/queue", response_model=List[OrderRead])
def list_manual_queue(
    strategy_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
) -> List[Order]:
    """Return orders currently in the manual WAITING queue."""

    query = db.query(Order).filter(
        Order.status == "WAITING",
        Order.mode == "MANUAL",
        Order.simulated.is_(False),
    )
    if strategy_id is not None:
        query = query.filter(Order.strategy_id == strategy_id)
    return query.order_by(Order.created_at).all()


@router.get("/{order_id}", response_model=OrderRead)
def get_order(order_id: int, db: Session = Depends(get_db)) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return order


@router.patch("/{order_id}/status", response_model=OrderRead)
def update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    db: Session = Depends(get_db),
) -> Order:
    """Minimal status update endpoint for manual queue workflows.

    For now we only support transitions between WAITING and CANCELLED,
    which is enough to model a basic manual queue cancel operation
    without touching broker integration.
    """

    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    if order.status not in {"WAITING", "CANCELLED"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only WAITING/CANCELLED orders can be updated via this endpoint.",
        )

    target_status = payload.status
    if order.status == target_status:
        return order

    order.status = target_status
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@router.patch("/{order_id}", response_model=OrderRead)
def edit_order(
    order_id: int,
    payload: OrderUpdate,
    db: Session = Depends(get_db),
) -> Order:
    """Edit basic fields for an order in the manual WAITING queue.

    We currently allow updating qty, price, order_type, and product for
    non-simulated manual orders that are still in WAITING state.
    """

    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    if order.status != "WAITING" or order.mode != "MANUAL" or order.simulated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only non-simulated WAITING MANUAL orders can be edited.",
        )

    updated = False

    if payload.qty is not None:
        if payload.qty <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quantity must be positive.",
            )
        order.qty = payload.qty
        updated = True

    if payload.order_type is not None:
        order_type = payload.order_type.upper()
        if order_type not in {"MARKET", "LIMIT"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="order_type must be MARKET or LIMIT.",
            )
        order.order_type = order_type
        updated = True

    if payload.price is not None:
        if payload.price < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Price must be non-negative.",
            )
        order.price = payload.price
        updated = True

    if payload.product is not None:
        product = payload.product.upper()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Product must be non-empty.",
            )
        order.product = product
        updated = True

    if payload.gtt is not None:
        order.gtt = payload.gtt
        updated = True

    if not updated:
        return order

    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@router.post("/{order_id}/execute", response_model=OrderRead)
def execute_order(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Order:
    """Send a manual queue order to Zerodha for execution.

    For S05/G03 this is a best-effort call:
    - Requires the order to be in WAITING/MANUAL mode and not simulated.
    - On success sets status to SENT and stores Zerodha order id.
    - On failure sets status to FAILED and records the error message.
    """

    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    if order.status != "WAITING" or order.mode != "MANUAL" or order.simulated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only non-simulated WAITING MANUAL orders can be executed.",
        )

    if order.qty is None or order.qty <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order has invalid quantity.",
        )

    # Apply risk checks before contacting Zerodha. This runs for both
    # manual queue execution and AUTO strategies (which call this endpoint
    # internally from the webhook handler).
    risk = evaluate_order_risk(db, order)
    if risk.blocked:
        order.status = "REJECTED_RISK"
        order.error_message = risk.reason
        db.add(order)
        db.commit()
        db.refresh(order)
        logger.warning(
            "Order rejected by risk engine",
            extra={
                "extra": {
                    "correlation_id": getattr(request.state, "correlation_id", None),
                    "order_id": order.id,
                    "reason": risk.reason,
                }
            },
        )
        record_system_event(
            db,
            level="WARNING",
            category="risk",
            message="Order rejected by risk engine",
            correlation_id=getattr(request.state, "correlation_id", None),
            details={"order_id": order.id, "reason": risk.reason},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order rejected by risk engine: {risk.reason}",
        )

    if risk.clamped and risk.final_qty != order.qty:
        order.qty = risk.final_qty
        # Preserve any previous error message but append the clamp note.
        clamp_note = risk.reason or "Order quantity clamped by risk engine."
        if order.error_message:
            order.error_message = f"{order.error_message}; {clamp_note}"
        else:
            order.error_message = clamp_note
        db.add(order)
        db.commit()
        db.refresh(order)

    symbol = order.symbol
    exchange = order.exchange or "NSE"
    if ":" in symbol:
        ex, ts = symbol.split(":", 1)
        exchange = ex
        tradingsymbol = ts
    else:
        tradingsymbol = symbol

    client = _get_zerodha_client(db, settings)

    def _place(
        *,
        variety: str,
    ):
        return client.place_order(
            tradingsymbol=tradingsymbol,
            transaction_type=order.side,
            quantity=int(order.qty),
            order_type=order.order_type,
            product=order.product,
            exchange=exchange,
            price=order.price if order.order_type == "LIMIT" else None,
            variety=variety,
        )

    try:
        result = _place(variety="regular")
    except Exception as exc:  # pragma: no cover - defensive
        message = str(exc)

        # Zerodha returns a specific hint when an order must be placed as
        # an AMO (off-market order). When we detect this, retry once with
        # variety="amo" instead of failing immediately.
        amo_hint_phrases = (
            "Try placing an AMO order",
            "markets are not open for trading today",
        )
        if any(phrase in message for phrase in amo_hint_phrases):
            logger.info(
                "Order failed with regular variety; retrying as AMO",
                extra={
                    "extra": {
                        "correlation_id": getattr(
                            request.state, "correlation_id", None
                        ),
                        "order_id": order.id,
                        "error": message,
                    }
                },
            )
            try:
                result = _place(variety="amo")
            except Exception as exc_amo:  # pragma: no cover - defensive
                order.status = "FAILED"
                order.error_message = str(exc_amo)
                db.add(order)
                db.commit()
                db.refresh(order)
                logger.error(
                    "Zerodha AMO order placement failed",
                    extra={
                        "extra": {
                            "correlation_id": getattr(
                                request.state, "correlation_id", None
                            ),
                            "order_id": order.id,
                            "error": str(exc_amo),
                        }
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Zerodha AMO order placement failed: {exc_amo}",
                ) from exc_amo
        else:
            order.status = "FAILED"
            order.error_message = message
            db.add(order)
            db.commit()
            db.refresh(order)
            logger.error(
                "Zerodha order placement failed",
                extra={
                    "extra": {
                        "correlation_id": getattr(
                            request.state, "correlation_id", None
                        ),
                        "order_id": order.id,
                        "error": message,
                    }
                },
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Zerodha order placement failed: {message}",
            ) from exc

    if order.status == "FAILED":
        order.status = "FAILED"
        order.error_message = order.error_message or "Unknown Zerodha error."
        db.add(order)
        db.commit()
        db.refresh(order)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Zerodha order placement failed.",
        )

    order.zerodha_order_id = result.order_id
    order.status = "SENT"
    order.error_message = None
    db.add(order)
    db.commit()
    db.refresh(order)
    record_system_event(
        db,
        level="INFO",
        category="order",
        message="Order sent to Zerodha",
        correlation_id=getattr(request.state, "correlation_id", None),
        details={
            "order_id": order.id,
            "zerodha_order_id": order.zerodha_order_id,
            "symbol": order.symbol,
            "side": order.side,
            "qty": order.qty,
        },
    )
    return order


__all__ = ["router"]
