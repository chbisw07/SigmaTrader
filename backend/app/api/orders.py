from __future__ import annotations

import inspect
import logging
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user, get_current_user_optional
from app.clients import ZerodhaClient
from app.config_files import load_app_config
from app.core.config import Settings, get_settings
from app.core.crypto import decrypt_token
from app.core.market_hours import is_market_open_now
from app.db.session import get_db
from app.models import BrokerConnection, Order, Strategy, User
from app.schemas.orders import (
    ManualOrderCreate,
    OrderRead,
    OrderStatusUpdate,
    OrderUpdate,
)
from app.services.broker_secrets import get_broker_secret
from app.services.paper_trading import submit_paper_order
from app.services.risk import evaluate_order_risk
from app.services.system_events import record_system_event

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()
logger = logging.getLogger(__name__)


def _ensure_supported_broker(broker_name: str) -> str:
    broker = (broker_name or "").strip().lower()
    try:
        cfg = load_app_config()
        supported = set(cfg.brokers)
    except Exception:
        # Tests and minimal deployments may not have config.json available.
        supported = {"zerodha"}
    if broker not in supported:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported broker: {broker}",
        )
    return broker


def _get_zerodha_client(
    db: Session,
    settings: Settings,
    user_id: int | None = None,
) -> ZerodhaClient:
    """Construct a ZerodhaClient from stored broker connection.

    This function is defined separately to make it easy to monkeypatch in tests.
    """

    q = db.query(BrokerConnection).filter(BrokerConnection.broker_name == "zerodha")
    if user_id is not None:
        q = q.filter(BrokerConnection.user_id == user_id)
    conn = q.order_by(BrokerConnection.updated_at.desc()).first()
    if conn is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zerodha is not connected.",
        )

    api_key = get_broker_secret(
        db,
        settings,
        broker_name="zerodha",
        key="api_key",
        user_id=conn.user_id,
    )
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zerodha API key is not configured. "
            "Please configure it in the broker settings.",
        )

    access_token = decrypt_token(settings, conn.access_token_encrypted)

    # Import lazily to keep tests independent of the real library.
    from kiteconnect import KiteConnect  # type: ignore[import]

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)

    client = ZerodhaClient(kite)
    # Expose broker-side account id on the client when available so that
    # callers (e.g. order execution) can stamp it onto orders.
    client.broker_user_id = getattr(conn, "broker_user_id", None)  # type: ignore[attr-defined]
    return client


def _get_broker_client(
    db: Session,
    settings: Settings,
    broker_name: str,
    user_id: int | None = None,
) -> ZerodhaClient:
    broker = _ensure_supported_broker(broker_name)
    if broker == "zerodha":
        # Tests may monkeypatch `_get_zerodha_client` with a 2-arg callable.
        try:
            sig = inspect.signature(_get_zerodha_client)
            if "user_id" in sig.parameters:
                return _get_zerodha_client(db, settings, user_id=user_id)
        except Exception:
            pass
        return _get_zerodha_client(db, settings)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Broker not implemented yet: {broker}",
    )


@router.get("/", response_model=List[OrderRead])
def list_orders(
    status: Annotated[Optional[str], Query()] = None,
    strategy_id: Annotated[Optional[int], Query()] = None,
    broker_name: Annotated[Optional[str], Query()] = None,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> List[Order]:
    """Return a simple order history list with basic filters."""

    query = db.query(Order)
    if user is not None:
        query = query.filter(
            (Order.user_id == user.id) | (Order.user_id.is_(None)),
        )
    if status is not None:
        query = query.filter(Order.status == status)
    if strategy_id is not None:
        query = query.filter(Order.strategy_id == strategy_id)
    if broker_name is not None:
        broker = _ensure_supported_broker(broker_name)
        query = query.filter(Order.broker_name == broker)
    return query.order_by(Order.created_at.desc()).all()


@router.post("/", response_model=OrderRead)
def create_manual_order(
    payload: ManualOrderCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Order:
    """Create a new manual WAITING order for the current user.

    The order is added to the manual queue and can be edited or executed
    via the existing queue workflow.
    """

    if payload.qty <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quantity must be positive.",
        )
    if payload.price is not None and payload.price < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Price must be non-negative.",
        )

    broker = _ensure_supported_broker(payload.broker_name)

    if payload.gtt and broker != "zerodha":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GTT is only supported for Zerodha in this version.",
        )

    if payload.gtt and payload.order_type != "LIMIT":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GTT is supported only for LIMIT orders.",
        )

    # Basic validation for stop-loss semantics so that obviously
    # inconsistent orders are rejected at creation time instead of
    # failing only when execution is attempted.
    trigger_price = payload.trigger_price
    if payload.order_type in {"SL", "SL-M"}:
        # For SL/SL-M orders, trigger price is mandatory and must be
        # strictly positive.
        if trigger_price is None or trigger_price <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Trigger price must be positive for SL/SL-M orders.",
            )
        if payload.order_type == "SL":
            if payload.price is None or payload.price <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Price must be positive for SL orders.",
                )
    elif payload.order_type == "LIMIT":
        if payload.price is None or payload.price <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Price must be positive for LIMIT orders.",
            )
    elif trigger_price is not None and trigger_price <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Trigger price must be positive when provided.",
        )

    order = Order(
        user_id=user.id,
        broker_name=broker,
        alert_id=None,
        strategy_id=None,
        symbol=payload.symbol,
        exchange=payload.exchange,
        side=payload.side,
        qty=payload.qty,
        price=payload.price,
        trigger_price=payload.trigger_price,
        trigger_percent=None,
        order_type=payload.order_type,
        product=payload.product,
        gtt=payload.gtt,
        status="WAITING",
        mode=payload.mode,
        execution_target=payload.execution_target,
        simulated=False,
    )

    db.add(order)
    db.commit()
    db.refresh(order)

    if payload.mode == "AUTO":
        try:
            execute_order(
                order_id=order.id,
                request=request,
                db=db,
                settings=settings,
            )
            db.refresh(order)
        except HTTPException as exc:
            # If execution failed before status transition (e.g. broker not
            # connected), mark the order as FAILED so it shows up in history.
            db.refresh(order)
            if order.status == "WAITING":
                order.status = "FAILED"
                order.error_message = (
                    exc.detail if isinstance(exc.detail, str) else str(exc.detail)
                )
                db.add(order)
                db.commit()
                db.refresh(order)
        except Exception as exc:  # pragma: no cover - defensive
            db.refresh(order)
            if order.status == "WAITING":
                order.status = "FAILED"
                order.error_message = str(exc)
                db.add(order)
                db.commit()
                db.refresh(order)
    return order


@router.get("/queue", response_model=List[OrderRead])
def list_manual_queue(
    strategy_id: Annotated[Optional[int], Query()] = None,
    broker_name: Annotated[Optional[str], Query()] = None,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> List[Order]:
    """Return orders currently in the manual WAITING queue."""

    query = db.query(Order).filter(
        Order.status == "WAITING",
        Order.mode == "MANUAL",
        Order.simulated.is_(False),
    )
    if user is not None:
        query = query.filter(
            (Order.user_id == user.id) | (Order.user_id.is_(None)),
        )
    if strategy_id is not None:
        query = query.filter(Order.strategy_id == strategy_id)
    if broker_name is not None:
        broker = _ensure_supported_broker(broker_name)
        query = query.filter(Order.broker_name == broker)
    return query.order_by(Order.created_at.desc()).all()


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

    We currently allow updating qty, price, trigger fields, order_type,
    and product for non-simulated manual orders that are still in
    WAITING state.
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

    if payload.price is not None:
        if payload.price < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Price must be non-negative.",
            )
        order.price = payload.price
        updated = True

    if payload.trigger_price is not None:
        if payload.trigger_price <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Trigger price must be positive.",
            )
        order.trigger_price = payload.trigger_price
        updated = True

    if payload.trigger_percent is not None:
        order.trigger_percent = payload.trigger_percent
        updated = True

    if payload.side is not None:
        side = payload.side.upper()
        if side not in {"BUY", "SELL"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="side must be BUY or SELL.",
            )
        order.side = side
        updated = True

    if payload.order_type is not None:
        order_type = payload.order_type.upper()
        if order_type not in {"MARKET", "LIMIT", "SL", "SL-M"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="order_type must be MARKET, LIMIT, SL, or SL-M.",
            )
        order.order_type = order_type
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


def execute_order_internal(
    order_id: int,
    *,
    db: Session,
    settings: Settings,
    correlation_id: str | None = None,
) -> Order:
    """Send a manual queue order to its configured broker for execution.

    For S05/G03 this is a best-effort call:
    - Requires the order to be in WAITING/MANUAL mode and not simulated.
    - On success sets status to SENT and stores Zerodha order id.
    - On failure sets status to FAILED and records the error message.
    """

    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    if order.status != "WAITING" or order.simulated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only non-simulated WAITING orders can be executed.",
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
                    "correlation_id": correlation_id,
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
            correlation_id=correlation_id,
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

    # Route PAPER strategies to the paper engine instead of Zerodha.
    exec_target = getattr(order, "execution_target", None) or "LIVE"
    if order.strategy is not None:
        exec_target = getattr(order.strategy, "execution_target", exec_target)
    else:
        # Fallback: when no strategy is attached, treat a single
        # configured strategy as the default execution_target so that
        # paper mode can still be used in simple setups.
        try:
            strategies: list[Strategy] = db.query(Strategy).all()
            if len(strategies) == 1:
                exec_target = strategies[0].execution_target
        except Exception:
            exec_target = "LIVE"

    if exec_target == "PAPER":
        if not is_market_open_now():
            order.simulated = True
            order.status = "FAILED"
            order.error_message = (
                "Paper order rejected: market is closed. "
                "Please place during trading hours or use GTT."
            )
            db.add(order)
            db.commit()
            db.refresh(order)
            record_system_event(
                db,
                level="WARNING",
                category="paper",
                message="Paper order rejected: market closed",
                correlation_id=correlation_id,
                details={
                    "order_id": order.id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "qty": order.qty,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Market is closed; paper order rejected.",
            )
        return submit_paper_order(
            db,
            settings,
            order,
            correlation_id=correlation_id,
        )

    symbol = order.symbol
    exchange = order.exchange or "NSE"
    if ":" in symbol:
        ex, ts = symbol.split(":", 1)
        exchange = ex
        tradingsymbol = ts
    else:
        tradingsymbol = symbol

    broker_name = _ensure_supported_broker(getattr(order, "broker_name", "zerodha"))
    if order.broker_name != broker_name:
        order.broker_name = broker_name
        db.add(order)
        db.commit()
        db.refresh(order)

    client = _get_broker_client(db, settings, broker_name, user_id=order.user_id)
    broker_account_id = getattr(client, "broker_user_id", None)
    if broker_account_id:
        order.broker_account_id = broker_account_id

    # Handle GTT orders by creating a Zerodha GTT instead of a
    # regular/AMO order. We currently support single-leg LIMIT GTTs
    # for equity; more advanced patterns (OCO, SL GTT) can be layered
    # on later.
    if order.gtt:
        if broker_name != "zerodha":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GTT is only supported for Zerodha in this version.",
            )
        if order.order_type != "LIMIT":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GTT orders are currently supported only for LIMIT order_type.",
            )
        if order.price is None or order.price <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Price must be positive for GTT LIMIT orders.",
            )

        # Use an explicit trigger price when provided; otherwise fall
        # back to the limit price so the GTT triggers when price
        # touches the order level.
        trigger_price = (
            float(order.trigger_price)
            if order.trigger_price is not None and order.trigger_price > 0
            else float(order.price)
        )

        try:
            last_price = client.get_ltp(exchange=exchange, tradingsymbol=tradingsymbol)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "Failed to fetch LTP for GTT placement",
                extra={
                    "extra": {
                        "correlation_id": correlation_id,
                        "symbol": symbol,
                        "error": str(exc),
                    }
                },
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to fetch LTP for GTT placement: {exc}",
            ) from exc

        try:
            gtt_result = client.place_gtt_single(
                tradingsymbol=tradingsymbol,
                exchange=exchange,
                transaction_type=order.side,
                quantity=order.qty,
                product=order.product,
                trigger_price=trigger_price,
                order_price=float(order.price),
                last_price=last_price,
            )
        except Exception as exc:  # pragma: no cover - defensive
            message = str(exc)
            order.status = "FAILED"
            order.error_message = message
            db.add(order)
            db.commit()
            db.refresh(order)
            logger.error(
                "Zerodha GTT placement failed",
                extra={
                    "extra": {
                        "correlation_id": correlation_id,
                        "order_id": order.id,
                        "error": message,
                    }
                },
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Zerodha GTT placement failed: {message}",
            ) from exc

        trigger_id = str(gtt_result.get("trigger_id") or gtt_result.get("id") or "")
        if trigger_id:
            order.broker_order_id = trigger_id
            order.zerodha_order_id = trigger_id
        order.status = "SENT"
        order.error_message = None
        db.add(order)
        db.commit()
        db.refresh(order)
        record_system_event(
            db,
            level="INFO",
            category="order",
            message="GTT created at Zerodha",
            correlation_id=correlation_id,
            details={
                "order_id": order.id,
                "broker_name": broker_name,
                "broker_order_id": order.broker_order_id,
                "symbol": order.symbol,
                "side": order.side,
                "qty": order.qty,
                "trigger_price": trigger_price,
                "price": order.price,
            },
        )
        return order

    # For SL/SL-M orders, validate trigger configuration and derive
    # trigger_percent relative to current LTP as a convenience for
    # later analytics and UI display. We also enforce basic guardrails
    # so that stop-loss orders are not obviously on the wrong side of
    # the market.
    if order.order_type in {"SL", "SL-M"}:
        if order.trigger_price is None or order.trigger_price <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Trigger price must be positive for SL/SL-M orders.",
            )
        if order.order_type == "SL":
            if order.price is None or order.price <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Price must be positive for SL orders.",
                )
        try:
            ltp = client.get_ltp(exchange=exchange, tradingsymbol=tradingsymbol)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "Failed to fetch LTP for stop-loss validation",
                extra={
                    "extra": {
                        "correlation_id": correlation_id,
                        "symbol": symbol,
                        "error": str(exc),
                    }
                },
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to fetch LTP for stop-loss validation: {exc}",
            ) from exc

        trigger = float(order.trigger_price)
        # Record trigger_percent relative to LTP so the UI can show a
        # human-friendly distance from the market at the time of
        # execution.
        if ltp > 0:
            order.trigger_percent = ((trigger - ltp) / ltp) * 100.0

        side = order.side.upper()
        if side == "BUY" and trigger < ltp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "For BUY SL/SL-M orders, trigger price should not be "
                    "below the current market price."
                ),
            )
        if side == "SELL" and trigger > ltp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "For SELL SL/SL-M orders, trigger price should not be "
                    "above the current market price."
                ),
            )

        db.add(order)
        db.commit()
        db.refresh(order)

    def _place(
        *,
        variety: str,
    ):
        trigger_price = (
            float(order.trigger_price)
            if order.order_type in {"SL", "SL-M"} and order.trigger_price is not None
            else None
        )
        price: float | None
        if order.order_type == "LIMIT":
            price = order.price
        elif order.order_type == "SL":
            price = order.price
        else:
            price = None

        return client.place_order(
            tradingsymbol=tradingsymbol,
            transaction_type=order.side,
            quantity=int(order.qty),
            order_type=order.order_type,
            product=order.product,
            exchange=exchange,
            price=price,
            trigger_price=trigger_price,
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
                        "correlation_id": correlation_id,
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
                            "correlation_id": correlation_id,
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
                        "correlation_id": correlation_id,
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

    order.broker_order_id = result.order_id
    if broker_name == "zerodha":
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
        message=f"Order sent to {broker_name}",
        correlation_id=correlation_id,
        details={
            "order_id": order.id,
            "broker_name": broker_name,
            "broker_order_id": order.broker_order_id,
            "symbol": order.symbol,
            "side": order.side,
            "qty": order.qty,
        },
    )
    return order


@router.post("/{order_id}/execute", response_model=OrderRead)
def execute_order(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Order:
    correlation_id = getattr(request.state, "correlation_id", None)
    return execute_order_internal(
        order_id,
        db=db,
        settings=settings,
        correlation_id=correlation_id,
    )


@router.post("/sync", response_model=dict)
def sync_orders(
    broker_name: Annotated[str, Query(min_length=1)] = "zerodha",
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> dict:
    """Synchronize local Order rows with broker order statuses."""

    broker = _ensure_supported_broker(broker_name)
    client = _get_broker_client(db, settings, broker, user_id=user.id)
    from app.services.order_sync import sync_order_statuses

    updated = sync_order_statuses(db, client, user_id=user.id)
    return {"updated": updated}


__all__ = ["router"]
