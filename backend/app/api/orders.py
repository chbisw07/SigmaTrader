from __future__ import annotations

import inspect
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session, joinedload

from app.api.auth import get_current_user, get_current_user_optional
from app.clients import AngelOneClient, AngelOneSession, ZerodhaClient
from app.config_files import load_app_config
from app.core.config import Settings, get_settings
from app.core.crypto import decrypt_token
from app.core.market_hours import is_market_open_now
from app.db.session import SessionLocal, get_db
from app.models import BrokerConnection, Group, Order, Position, Strategy, User
from app.schemas.orders import (
    ManualOrderCreate,
    OrderRead,
    OrderStatusUpdate,
    OrderUpdate,
)
from app.services.broker_instruments import resolve_broker_symbol_and_token
from app.services.broker_secrets import get_broker_secret
from app.services.execution_policy_state import (
    ExecutionPolicyParams,
    apply_post_trade_updates_on_execution_unified,
    get_or_create_execution_state,
    interval_minutes_for_order,
    resolve_interval_for_order,
    scope_key_for_order,
    DEFAULT_INFLIGHT_TTL_SECONDS,
)
from app.services.instruments_sync import sync_smartapi_instrument_master
from app.services.paper_trading import submit_paper_order
from app.services.price_ticks import round_price_to_tick
from app.services.risk_unified_store import read_unified_risk_global
from app.services.system_events import record_system_event

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()
logger = logging.getLogger(__name__)

# How long to wait (best-effort) when execution-policy state indicates another
# execution is inflight for the same scope key. This is a concurrency guard to
# avoid races; we prefer waiting briefly over permanently rejecting.
DEFAULT_EXECUTION_POLICY_CONCURRENCY_WAIT_SECONDS = 6.0
DEFAULT_EXECUTION_POLICY_CONCURRENCY_SLEEP_SECONDS = 0.15


def _now_utc() -> datetime:
    return datetime.now(UTC)


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


def _get_angelone_client(
    db: Session,
    settings: Settings,
    user_id: int | None = None,
) -> AngelOneClient:
    q = db.query(BrokerConnection).filter(BrokerConnection.broker_name == "angelone")
    if user_id is not None:
        q = q.filter(BrokerConnection.user_id == user_id)
    conn = q.order_by(BrokerConnection.updated_at.desc()).first()
    if conn is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AngelOne is not connected.",
        )

    api_key = get_broker_secret(
        db,
        settings,
        broker_name="angelone",
        key="api_key",
        user_id=conn.user_id,
    )
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SmartAPI API key is not configured. "
            "Please configure it in the broker settings.",
        )

    raw = decrypt_token(settings, conn.access_token_encrypted)
    try:
        parsed = json.loads(raw) if raw else {}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"AngelOne session is invalid: {exc}",
        ) from exc

    jwt = str(parsed.get("jwt_token") or "")
    if not jwt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AngelOne session is missing jwt_token. Please reconnect.",
        )

    session = AngelOneSession(
        jwt_token=jwt,
        refresh_token=str(parsed.get("refresh_token") or "") or None,
        feed_token=str(parsed.get("feed_token") or "") or None,
        client_code=str(parsed.get("client_code") or "") or None,
    )
    client = AngelOneClient(api_key=api_key, session=session)
    client.broker_user_id = getattr(conn, "broker_user_id", None)  # type: ignore[attr-defined]
    return client


def _get_broker_client(
    db: Session,
    settings: Settings,
    broker_name: str,
    user_id: int | None = None,
) -> ZerodhaClient | AngelOneClient:
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
    if broker == "angelone":
        return _get_angelone_client(db, settings, user_id=user_id)
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

    query = db.query(Order).options(joinedload(Order.alert))
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

    price = round_price_to_tick(payload.price)
    trigger_price = round_price_to_tick(payload.trigger_price)

    broker = _ensure_supported_broker(payload.broker_name)

    portfolio_group_id: int | None = None
    if getattr(payload, "portfolio_group_id", None) is not None:
        try:
            portfolio_group_id = int(payload.portfolio_group_id)  # type: ignore[attr-defined]
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="portfolio_group_id must be an integer.",
            ) from exc
        group = db.get(Group, portfolio_group_id)
        if group is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Portfolio group not found: {portfolio_group_id}",
            )
        if group.kind != "PORTFOLIO":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Group {portfolio_group_id} is not a PORTFOLIO.",
            )
        if group.owner_id is not None and group.owner_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden.",
            )

    if payload.gtt and payload.order_type != "LIMIT":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GTT is supported only for LIMIT orders.",
        )
    if payload.gtt and (price is None or price <= 0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Price must be positive for GTT LIMIT orders.",
        )

    # Basic validation for stop-loss semantics so that obviously
    # inconsistent orders are rejected at creation time instead of
    # failing only when execution is attempted.
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
        if price is None or price <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Price must be positive for LIMIT orders.",
            )
    elif trigger_price is not None and trigger_price <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Trigger price must be positive when provided.",
        )

    # For GTT / conditional orders, default trigger to the limit price when
    # not provided so that the condition is well-defined.
    if payload.gtt and (trigger_price is None or trigger_price <= 0) and price:
        trigger_price = float(price)

    synthetic_gtt = bool(payload.gtt and broker != "zerodha")
    armed_at = None
    if synthetic_gtt and payload.mode == "AUTO":
        armed_at = _now_utc()

    risk_spec_json = (
        payload.risk_spec.to_json() if payload.risk_spec is not None else None
    )
    order = Order(
        user_id=user.id,
        broker_name=broker,
        alert_id=None,
        strategy_id=None,
        portfolio_group_id=portfolio_group_id,
        symbol=payload.symbol,
        exchange=payload.exchange,
        side=payload.side,
        qty=payload.qty,
        price=price,
        trigger_price=trigger_price,
        trigger_percent=None,
        order_type=payload.order_type,
        product=payload.product,
        gtt=payload.gtt,
        synthetic_gtt=synthetic_gtt,
        armed_at=armed_at,
        status="WAITING",
        mode=payload.mode,
        execution_target=payload.execution_target,
        simulated=False,
        risk_spec_json=risk_spec_json,
        is_exit=False,
    )

    db.add(order)
    db.commit()
    db.refresh(order)

    # AUTO semantics:
    # - Non-GTT orders: execute immediately.
    # - Zerodha GTT: place the broker-side GTT immediately.
    # - Synthetic (non-Zerodha) conditional orders: "AUTO" arms the condition,
    #   but does not send an order to the broker until triggered.
    should_auto_execute = payload.mode == "AUTO" and not synthetic_gtt
    if should_auto_execute:
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

    query = (
        db.query(Order)
        .options(joinedload(Order.alert))
        .filter(
            Order.status == "WAITING",
            Order.mode == "MANUAL",
            Order.simulated.is_(False),
        )
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
        order.price = round_price_to_tick(payload.price)
        updated = True

    if payload.trigger_price is not None:
        if payload.trigger_price <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Trigger price must be positive.",
            )
        order.trigger_price = round_price_to_tick(payload.trigger_price)
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
        if not order.gtt:
            order.synthetic_gtt = False
            order.trigger_operator = None
            order.armed_at = None
            order.last_checked_at = None
            order.last_seen_price = None
            order.triggered_at = None
        else:
            raw = getattr(order, "broker_name", "zerodha")
            broker_name = _ensure_supported_broker(raw)
            order.synthetic_gtt = broker_name != "zerodha"
        updated = True

    if payload.execution_target is not None:
        target = str(payload.execution_target).strip().upper()
        if target not in {"LIVE", "PAPER"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="execution_target must be LIVE or PAPER.",
            )
        order.execution_target = target
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

    now_utc = _now_utc()
    risk_global = read_unified_risk_global(db)
    risk_profile_id: int | None = None
    risk_baseline_equity: float | None = None
    execution_policy_key = None
    execution_policy_interval_min: int | None = None
    execution_policy_apply = False

    allowed_status = {"WAITING"}
    if order.synthetic_gtt:
        allowed_status = {"WAITING", "SENDING"}
    if order.status not in allowed_status or order.simulated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only non-simulated WAITING orders can be executed.",
        )

    # Execution policy state:
    # - Used as a concurrency guard (inflight marker) when Risk Settings are enabled.
    # - Never blocks structural exits (exposure-reducing orders).
    # - Skips conditional/GTT arming (no immediate broker execution).
    is_synthetic_gtt_arm = bool(
        order.gtt and order.synthetic_gtt and order.status == "WAITING"
    )
    is_broker_gtt = bool(order.gtt and not order.synthetic_gtt)

    def _is_explicit_manual_order() -> bool:
        return bool(
            getattr(order, "alert_id", None) is None
            and getattr(order, "strategy_id", None) is None
            and getattr(order, "portfolio_group_id", None) is None
        )

    # Execution policy state is used as a concurrency guard (inflight marker) to avoid
    # races when multiple orders attempt to execute for the same scope key.
    execution_policy_apply = bool(
        bool(risk_global.enabled) and not bool(is_synthetic_gtt_arm or is_broker_gtt)
    )
    if execution_policy_apply:
        key = scope_key_for_order(order)
        interval_hint, interval_hint_source = resolve_interval_for_order(order, None)

        # Conservative structural-exit detection: never block protective reductions.
        treat_as_exit = bool(getattr(order, "is_exit", False))
        if not treat_as_exit:
            try:
                sym = str(getattr(order, "symbol", "") or "").strip()
                exch = str(getattr(order, "exchange", "") or "NSE").strip().upper()
                if ":" in sym:
                    ex2, ts2 = sym.split(":", 1)
                    exch = (ex2 or exch).strip().upper()
                    sym = (ts2 or sym).strip()
                pos = (
                    db.query(Position)
                    .filter(
                        Position.broker_name
                        == str(getattr(order, "broker_name", "zerodha")).strip().lower(),
                        Position.symbol == sym,
                        Position.exchange == exch,
                        Position.product
                        == str(getattr(order, "product", "MIS")).strip().upper(),
                    )
                    .one_or_none()
                )
                if pos is not None:
                    pos_qty = float(getattr(pos, "qty", 0.0) or 0.0)
                    delta = (
                        float(order.qty or 0.0)
                        if str(order.side).strip().upper() == "BUY"
                        else -float(order.qty or 0.0)
                    )
                    if abs(pos_qty + delta) < abs(pos_qty):
                        treat_as_exit = True
            except Exception:
                pass

        if not treat_as_exit:
            # Use a short-lived session to acquire an inflight reservation in a fresh
            # SQLite transaction (avoids snapshot/lost-update anomalies under threads).
            from sqlalchemy import and_, or_, text

            from app.models import ExecutionPolicyState

            reason_code = "RISK_POLICY_CONCURRENT_EXECUTION"
            message = "Another order execution is in progress for this scope key."

            wait_deadline_mono = time.monotonic() + float(
                DEFAULT_EXECUTION_POLICY_CONCURRENCY_WAIT_SECONDS
            )
            acquired = False
            while time.monotonic() < wait_deadline_mono:
                guard_now = _now_utc()
                expires_at = guard_now + timedelta(seconds=int(DEFAULT_INFLIGHT_TTL_SECONDS))

                try:
                    with SessionLocal() as guard_db:
                        if (
                            guard_db.bind is not None
                            and guard_db.bind.dialect.name == "sqlite"
                        ):
                            # Ensures the UPDATE sees the latest committed inflight flag.
                            guard_db.execute(text("BEGIN IMMEDIATE"))
                        state_guard = get_or_create_execution_state(
                            guard_db,
                            key=key,
                            now_utc=guard_now,
                            interval_minutes=interval_hint,
                            interval_source=interval_hint_source,
                            lock=True,
                        )
                        updated = (
                            guard_db.query(ExecutionPolicyState)
                            .filter(
                                ExecutionPolicyState.id == int(state_guard.id),
                                or_(
                                    ExecutionPolicyState.inflight_order_id.is_(None),
                                    ExecutionPolicyState.inflight_order_id
                                    == int(order.id),
                                    and_(
                                        ExecutionPolicyState.inflight_expires_at.isnot(
                                            None
                                        ),
                                        ExecutionPolicyState.inflight_expires_at
                                        <= guard_now,
                                    ),
                                ),
                            )
                            .update(
                                {
                                    ExecutionPolicyState.inflight_order_id: int(
                                        order.id
                                    ),
                                    ExecutionPolicyState.inflight_started_at: guard_now,
                                    ExecutionPolicyState.inflight_expires_at: expires_at,
                                },
                                synchronize_session=False,
                            )
                        )
                        guard_db.commit()

                    if int(updated or 0) == 1:
                        acquired = True
                        break
                except Exception:
                    acquired = False

                time.sleep(float(DEFAULT_EXECUTION_POLICY_CONCURRENCY_SLEEP_SECONDS))

            if not acquired:
                record_system_event(
                    db,
                    level="WARNING",
                    category="risk",
                    message="Order deferred by risk engine (concurrent execution)",
                    correlation_id=correlation_id,
                    details={
                        "order_id": int(order.id),
                        "reason_code": reason_code,
                        "message": message,
                        "strategy_ref": key.strategy_ref,
                        "symbol": key.symbol,
                        "product": key.product,
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "status": "busy",
                        "reason_code": reason_code,
                        "message": message,
                    },
                )

        state = get_or_create_execution_state(
            db,
            key=key,
            now_utc=now_utc,
            interval_minutes=interval_hint,
            interval_source=interval_hint_source,
            lock=True,
        )
        interval_min, interval_source = resolve_interval_for_order(order, state)

        # Keep interval stable per key but adopt a better signal when available.
        if interval_min and int(state.interval_minutes or 0) != int(interval_min):
            state.interval_minutes = int(interval_min)
        if interval_source and str(getattr(state, "interval_source", "") or "") != str(
            interval_source
        ):
            state.interval_source = str(interval_source)
        if (
            interval_source == "default_fallback"
            and not bool(getattr(state, "default_interval_logged", False))
        ):
            state.default_interval_logged = True
            record_system_event(
                db,
                level="INFO",
                category="risk",
                message="Execution policy interval defaulted to fallback",
                correlation_id=correlation_id,
                details={
                    "strategy_ref": key.strategy_ref,
                    "symbol": key.symbol,
                    "product": key.product,
                    "interval_minutes": int(interval_min),
                    "interval_source": interval_source,
                },
            )

        # Clear stale inflight reservations (defensive for crashes/timeouts).
        try:
            inflight_expires = getattr(state, "inflight_expires_at", None)
            if inflight_expires is not None and now_utc >= inflight_expires:
                state.inflight_order_id = None
                state.inflight_started_at = None
                state.inflight_expires_at = None
        except Exception:
            pass

        db.add(state)
        db.commit()
        execution_policy_key = key
        execution_policy_interval_min = int(interval_min)

    # Apply risk checks before contacting the broker (covers manual executes,
    # webhook AUTO, and other internal flows). When manual_override_enabled is ON,
    # explicitly user-created manual orders can bypass risk blocks.
    #
    # This is the single enforcement choke-point: legacy RiskPolicy enforcement is not
    # consulted at execute-time (settings UI is unified around globals + profiles +
    # source overrides).
    if bool(risk_global.enabled):
        try:
            from app.services.risk_engine import evaluate_order_risk, record_decision_log

            user_obj = db.get(User, order.user_id) if order.user_id is not None else None

            product_hint: str | None = None
            try:
                if order.alert is not None and getattr(order.alert, "raw_payload", None):
                    raw = str(order.alert.raw_payload)
                    if raw.strip().startswith("{"):
                        data = json.loads(raw)
                        if isinstance(data, dict):
                            trade_details = data.get("trade_details")
                            if not isinstance(trade_details, dict):
                                trade_details = {}
                            signal = data.get("signal")
                            if not isinstance(signal, dict):
                                signal = {}
                            hints = data.get("hints")
                            if not isinstance(hints, dict):
                                hints = {}
                            product_hint = (
                                data.get("product_hint")
                                or signal.get("product_hint")
                                or hints.get("product_hint")
                                or trade_details.get("product")
                            )
            except Exception:
                product_hint = None

            # If the TradingView payload omitted product, fall back to the order's
            # current product so the risk engine selects the corresponding profile.
            if not product_hint:
                try:
                    product_hint = (getattr(order, "product", None) or "").strip().upper() or None
                except Exception:
                    product_hint = None

            baseline_equity = float(risk_global.baseline_equity_inr or 0.0)
            decision = evaluate_order_risk(
                db,
                settings,
                user=user_obj,
                order=order,
                baseline_equity=baseline_equity,
                now_utc=now_utc,
                product_hint=product_hint,
            )
            risk_profile_id = decision.risk_profile_id
            risk_baseline_equity = baseline_equity
            # Shared compiler output used by the UI "Effective Risk Summary" panel.
            # Keep the execution path aligned by invoking the same compiler logic
            # used by the UI "Effective Risk Summary" panel (tests assert this).
            try:
                from app.services.risk_compiler import compile_risk_policy

                if decision.resolved_product and decision.risk_category:
                    compile_risk_policy(
                        db,
                        settings,
                        user=user_obj,
                        product=str(decision.resolved_product).strip().upper(),
                        category=str(decision.risk_category).strip().upper(),
                        scenario=None,
                        symbol=str(getattr(order, "symbol", None) or "") or None,
                        strategy_id=str(getattr(order.alert, "strategy_id", None) or "") or None,
                    )
            except Exception:
                pass
            record_decision_log(
                db,
                user_id=(user_obj.id if user_obj is not None else order.user_id),
                alert=order.alert,
                order=order,
                decision=decision,
                product_hint=product_hint,
            )

            if decision.blocked:
                reason = "; ".join([r for r in decision.reasons if r]) or "Blocked by risk engine."
                if bool(risk_global.manual_override_enabled) and _is_explicit_manual_order():
                    # Presidential authority: allow execution, but annotate + audit (decision log already recorded).
                    note = f"Manual override enabled: {reason}"
                    order.error_message = f"{order.error_message}; {note}" if order.error_message else note
                    db.add(order)
                    db.commit()
                    db.refresh(order)
                else:
                    order.status = "REJECTED_RISK"
                    order.error_message = reason
                    db.add(order)
                    db.commit()
                    db.refresh(order)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Order rejected by risk engine: {reason}",
                    )

            changed = False
            if decision.resolved_product and decision.resolved_product != order.product:
                order.product = decision.resolved_product
                changed = True
            if decision.final_order_type and decision.final_order_type != order.order_type:
                order.order_type = decision.final_order_type
                changed = True
            if decision.final_price and (order.price is None or float(order.price or 0.0) <= 0):
                order.price = float(decision.final_price)
                changed = True
            if (
                decision.final_qty
                and float(decision.final_qty) > 0
                and (
                    order.qty is None
                    or float(order.qty or 0.0) <= 0
                    or float(order.qty or 0.0) != float(decision.final_qty)
                )
            ):
                # Never auto-resize explicit manual orders when manual override is enabled.
                if not (bool(risk_global.manual_override_enabled) and _is_explicit_manual_order()):
                    order.qty = float(decision.final_qty)
                    changed = True
            if changed:
                db.add(order)
                db.commit()
                db.refresh(order)
        except HTTPException:
            raise
        except Exception as exc:
            # Fail closed: if risk is enabled but errors, block execution.
            order.status = "REJECTED_RISK"
            order.error_message = f"Risk engine error: {exc}"
            db.add(order)
            db.commit()
            db.refresh(order)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Order rejected by risk engine (internal error).",
            ) from exc

    if order.qty is None or order.qty <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order has invalid quantity.",
        )

    def _release_execution_policy_inflight() -> None:
        if not execution_policy_apply or execution_policy_key is None:
            return
        try:
            interval_min = int(execution_policy_interval_min or 5)
            state = get_or_create_execution_state(
                db,
                key=execution_policy_key,
                now_utc=now_utc,
                interval_minutes=interval_min,
                lock=True,
            )
            if getattr(state, "inflight_order_id", None) is not None and int(
                state.inflight_order_id  # type: ignore[arg-type]
            ) == int(order.id):
                state.inflight_order_id = None
                state.inflight_started_at = None
                state.inflight_expires_at = None
                db.add(state)
                db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

    # Enforce tick-size rounding on all persisted orders (defensive for legacy
    # rows created before rounding was introduced).
    rounded_price = round_price_to_tick(order.price)
    rounded_trigger_price = round_price_to_tick(order.trigger_price)
    if rounded_price != order.price or rounded_trigger_price != order.trigger_price:
        order.price = rounded_price
        order.trigger_price = rounded_trigger_price
        db.add(order)
        db.commit()
        db.refresh(order)

    # Route PAPER orders/strategies to the paper engine instead of the broker.
    # Precedence:
    # - Per-order execution_target='PAPER' always forces paper execution.
    # - Otherwise, fall back to the attached strategy's execution_target (if any),
    #   or (in single-strategy deployments) the only configured strategy.
    exec_target = (getattr(order, "execution_target", None) or "LIVE").strip().upper()
    if exec_target != "PAPER":
        if order.strategy is not None:
            exec_target = (
                getattr(order.strategy, "execution_target", exec_target) or exec_target
            )
        else:
            # Fallback: when no strategy is attached, treat a single configured
            # strategy as the default execution_target so that paper mode can
            # still be used in simple setups.
            try:
                strategies: list[Strategy] = db.query(Strategy).all()
                if len(strategies) == 1:
                    exec_target = strategies[0].execution_target
            except Exception:
                exec_target = "LIVE"
        exec_target = str(exec_target).strip().upper() or "LIVE"

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
            _release_execution_policy_inflight()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Market is closed; paper order rejected.",
            )
        order = submit_paper_order(
            db,
            settings,
            order,
            correlation_id=correlation_id,
        )
        if execution_policy_apply and execution_policy_key is not None:
            key = execution_policy_key
            interval_min = int(
                execution_policy_interval_min
                or interval_minutes_for_order(order, None)
            )
            state = get_or_create_execution_state(
                db,
                key=key,
                now_utc=now_utc,
                interval_minutes=interval_min,
                lock=True,
            )
            interval_eff, interval_src = resolve_interval_for_order(order, state)
            if interval_eff and int(state.interval_minutes or 0) != int(interval_eff):
                state.interval_minutes = int(interval_eff)
            if interval_src and str(getattr(state, "interval_source", "") or "") != str(
                interval_src
            ):
                state.interval_source = str(interval_src)
            price_for_pnl = float(order.price) if order.price else None
            apply_post_trade_updates_on_execution_unified(
                ExecutionPolicyParams(enabled=True),
                state,
                now_utc=now_utc,
                side=str(order.side),
                qty=float(order.qty or 0.0),
                exec_price=price_for_pnl,
            )
            if (
                getattr(state, "inflight_order_id", None) is not None
                and int(state.inflight_order_id) == int(order.id)
            ):  # type: ignore[arg-type]
                state.inflight_order_id = None
                state.inflight_started_at = None
                state.inflight_expires_at = None
            db.add(state)
            db.commit()
        return order

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

    def _sync_for_managed_risk() -> None:
        if not getattr(order, "risk_spec_json", None):
            return
        try:
            if broker_name == "zerodha":
                from app.services.order_sync import sync_order_statuses

                sync_order_statuses(db, client, user_id=order.user_id)  # type: ignore[arg-type]
            elif broker_name == "angelone":
                from app.services.order_sync_angelone import (
                    sync_order_statuses_angelone,
                )

                sync_order_statuses_angelone(db, client, user_id=order.user_id)  # type: ignore[arg-type]
            db.refresh(order)
        except Exception:
            return

    exchange_u = (exchange or "NSE").strip().upper()
    broker_tradingsymbol = tradingsymbol
    angelone_token: str | None = None
    if broker_name == "angelone":
        resolved = resolve_broker_symbol_and_token(
            db,
            broker_name="angelone",
            exchange=exchange_u,
            symbol=tradingsymbol.strip().upper(),
        )
        if resolved is None:
            # Best-effort: the SmartAPI scrip master is public; sync once so
            # newly-traded symbols can be resolved without manual intervention.
            try:
                sync_smartapi_instrument_master(db, settings)
            except Exception:
                # Fall through to the original error below.
                pass
            resolved = resolve_broker_symbol_and_token(
                db,
                broker_name="angelone",
                exchange=exchange_u,
                symbol=tradingsymbol.strip().upper(),
            )
        if resolved is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "AngelOne instrument mapping not found for "
                    f"{exchange_u}:{tradingsymbol}. "
                    "Please run Instruments → Sync for AngelOne."
                ),
            )
        broker_tradingsymbol, angelone_token = resolved

    # Synthetic GTT (SigmaTrader-managed conditional):
    # - In WAITING: "execute" means "arm" the condition (no broker call).
    # - In SENDING: order has been triggered by the scheduler; proceed to
    #   place a regular order at the destination broker.
    if order.gtt and order.synthetic_gtt and order.status == "WAITING":
        if order.order_type != "LIMIT":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Conditional orders are supported only for LIMIT order_type.",
            )
        if order.price is None or order.price <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Price must be positive for conditional LIMIT orders.",
            )
        if order.trigger_price is None or order.trigger_price <= 0:
            order.trigger_price = float(order.price)

        # Best-effort: derive trigger operator relative to current LTP when
        # arming so that the condition is deterministic.
        if not order.trigger_operator:
            try:
                if broker_name == "angelone":
                    if angelone_token is None:
                        raise RuntimeError("Missing AngelOne symbol token.")
                    ltp = client.get_ltp(  # type: ignore[call-arg]
                        exchange=exchange_u,
                        tradingsymbol=broker_tradingsymbol,
                        symboltoken=angelone_token,
                    )
                else:
                    ltp = client.get_ltp(  # type: ignore[call-arg]
                        exchange=exchange,
                        tradingsymbol=tradingsymbol,
                    )
                trigger = float(order.trigger_price)
                order.trigger_operator = ">=" if trigger >= float(ltp) else "<="
            except Exception:
                # If we can't fetch LTP now, we'll derive operator on the first
                # scheduler check.
                order.trigger_operator = None

        if order.armed_at is None:
            order.armed_at = _now_utc()
        order.error_message = None
        db.add(order)
        db.commit()
        db.refresh(order)
        record_system_event(
            db,
            level="INFO",
            category="order",
            message="Conditional order armed (SigmaTrader-managed)",
            correlation_id=correlation_id,
            details={
                "order_id": order.id,
                "broker_name": broker_name,
                "symbol": order.symbol,
                "side": order.side,
                "qty": order.qty,
                "trigger_price": order.trigger_price,
                "price": order.price,
            },
        )
        return order

    # Risk engine broker-aware guards (MIS-only, entries only).
    #
    # IMPORTANT: manual override (manual orders only) bypasses all risk enforcement,
    # including broker-aware guards. Structural validation still applies.
    if (
        risk_profile_id is not None
        and bool(risk_global.enabled)
        and not (bool(risk_global.manual_override_enabled) and _is_explicit_manual_order())
    ):
        from app.models import RiskProfile

        def _reject_guard(detail: str) -> None:
            order.status = "REJECTED_RISK"
            order.error_message = detail
            db.add(order)
            db.commit()
            db.refresh(order)
            record_system_event(
                db,
                level="WARNING",
                category="risk",
                message="Order rejected by risk engine (broker-aware guards)",
                correlation_id=correlation_id,
                details={"order_id": order.id, "reason": detail},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Order rejected by risk engine: {detail}",
            )

        profile = db.get(RiskProfile, int(risk_profile_id))
        if profile is None:
            _reject_guard("RiskProfile is missing.")

        is_exit_reduce = bool(getattr(order, "is_exit", False))
        if not is_exit_reduce:
            try:
                pos = (
                    db.query(Position)
                    .filter(
                        Position.broker_name == broker_name,
                        Position.symbol == tradingsymbol.strip().upper(),
                        Position.exchange == exchange_u,
                        Position.product == str(getattr(order, "product", "MIS")).strip().upper(),
                    )
                    .one_or_none()
                )
                pos_qty = float(getattr(pos, "qty", 0.0) or 0.0) if pos is not None else 0.0
                side = str(getattr(order, "side", "") or "").strip().upper()
                qty = float(getattr(order, "qty", 0.0) or 0.0)
                delta = qty if side == "BUY" else -qty if side == "SELL" else 0.0
                if abs(pos_qty + delta) < abs(pos_qty):
                    is_exit_reduce = True
            except Exception:
                is_exit_reduce = bool(getattr(order, "is_exit", False))

        if not is_exit_reduce and str(getattr(order, "product", "MIS")).strip().upper() == "MIS":
            # Fetch last price and previous close (when available).
            last_price: float | None = None
            prev_close: float | None = None
            try:
                if broker_name == "angelone":
                    if angelone_token is None:
                        raise RuntimeError("Missing AngelOne symbol token.")
                    last_price = float(
                        client.get_ltp(  # type: ignore[call-arg]
                            exchange=exchange_u,
                            tradingsymbol=broker_tradingsymbol,
                            symboltoken=angelone_token,
                        )
                    )
                else:
                    quote_bulk = getattr(client, "get_quote_bulk", None)
                    if callable(quote_bulk):
                        out = quote_bulk([(exchange, tradingsymbol)])
                        q = out.get((exchange, tradingsymbol)) or {}
                        last_price = float(q.get("last_price") or 0.0)
                        pc = q.get("prev_close")
                        prev_close = float(pc) if pc is not None else None
                    else:
                        last_price = float(
                            client.get_ltp(exchange=exchange, tradingsymbol=tradingsymbol)  # type: ignore[call-arg]
                        )
            except Exception as exc:
                _reject_guard(f"Failed to fetch LTP for risk checks: {exc}")

            if last_price is None or last_price <= 0:
                _reject_guard("Failed to fetch LTP for risk checks.")

            gap_guard_pct = float(getattr(profile, "gap_guard_pct", 0.0) or 0.0)
            if gap_guard_pct > 0:
                if prev_close is None or prev_close <= 0:
                    _reject_guard("Gap guard enabled but previous close is unavailable.")
                gap_pct = abs(last_price - float(prev_close)) / float(prev_close) * 100.0
                if gap_pct > gap_guard_pct:
                    _reject_guard(
                        f"Gap guard triggered ({gap_pct:.2f}% > {gap_guard_pct:.2f}%)."
                    )

            slippage_guard_bps = float(getattr(profile, "slippage_guard_bps", 0.0) or 0.0)
            if slippage_guard_bps > 0:
                ref = None
                if getattr(order, "trigger_price", None) is not None and float(order.trigger_price or 0.0) > 0:
                    ref = float(order.trigger_price)
                elif getattr(order, "price", None) is not None and float(order.price or 0.0) > 0:
                    ref = float(order.price)
                if not ref or ref <= 0:
                    _reject_guard("Slippage guard enabled but trigger/price is missing.")
                dev_bps = abs(last_price - ref) / ref * 10000.0
                if dev_bps > slippage_guard_bps:
                    _reject_guard(
                        f"Slippage guard triggered ({dev_bps:.1f} bps > {slippage_guard_bps:.1f} bps)."
                    )

            leverage_mode = str(getattr(profile, "leverage_mode", "") or "AUTO").strip().upper()
            if leverage_mode not in {"AUTO", "STATIC", "OFF"}:
                _reject_guard(f"Invalid leverage_mode: {leverage_mode}.")
            if leverage_mode != "OFF":
                max_lev = float(getattr(profile, "max_effective_leverage", 0.0) or 0.0)
                max_margin_pct = float(getattr(profile, "max_margin_used_pct", 0.0) or 0.0)
                baseline_equity = float(risk_baseline_equity or 0.0)
                if max_lev <= 0 or max_margin_pct <= 0 or baseline_equity <= 0:
                    _reject_guard(
                        "MIS leverage settings missing/invalid (set leverage_mode, "
                        "max_effective_leverage, max_margin_used_pct, and manual equity)."
                    )

                cap_trade = float(getattr(profile, "capital_per_trade", 0.0) or 0.0)
                cap_portfolio = baseline_equity * max_margin_pct / 100.0

                order_type = str(getattr(order, "order_type", "MARKET") or "MARKET").strip().upper()
                order_price = float(getattr(order, "price", 0.0) or 0.0)
                notional_px = order_price if order_type != "MARKET" and order_price > 0 else float(last_price)
                qty_f = float(getattr(order, "qty", 0.0) or 0.0)
                if qty_f <= 0:
                    _reject_guard("Invalid quantity for MIS margin checks.")
                notional = qty_f * notional_px

                required_margin = None
                if leverage_mode == "STATIC":
                    required_margin = notional
                else:
                    if broker_name != "zerodha" or not callable(getattr(client, "order_margins", None)):
                        _reject_guard(
                            "AUTO leverage mode requires Zerodha order_margins support."
                        )
                    preview_order: dict[str, Any] = {
                        "exchange": exchange,
                        "tradingsymbol": tradingsymbol,
                        "transaction_type": str(order.side).upper(),
                        "quantity": int(qty_f),
                        "product": str(order.product).upper(),
                        "order_type": order_type,
                        "variety": "regular",
                    }
                    if order_price > 0:
                        preview_order["price"] = order_price
                    if getattr(order, "trigger_price", None) is not None and float(order.trigger_price or 0.0) > 0:
                        preview_order["trigger_price"] = float(order.trigger_price)
                    preview_list = client.order_margins([preview_order])  # type: ignore[call-arg]
                    if not preview_list:
                        _reject_guard("Broker did not return margin preview.")
                    entry = preview_list[0]
                    required_raw = entry.get("total") or entry.get("margin") or 0.0
                    required_margin = float(required_raw or 0.0)

                if required_margin is None or required_margin <= 0:
                    _reject_guard("Invalid margin requirement from broker.")

                eff_lev = notional / required_margin if required_margin > 0 else 0.0
                if eff_lev > max_lev:
                    _reject_guard(
                        f"Effective leverage exceeds cap ({eff_lev:.2f} > {max_lev:.2f})."
                    )

                limit = min(cap_trade, cap_portfolio)
                if limit > 0 and required_margin > limit and qty_f > 0:
                    factor = limit / required_margin
                    old_qty = float(qty_f)
                    new_qty = int(old_qty * factor)
                    if new_qty <= 0:
                        _reject_guard(
                            "MIS margin caps reduce quantity to 0; increase capital_per_trade or limits."
                        )
                    order.qty = float(new_qty)
                    db.add(order)
                    db.commit()
                    db.refresh(order)
                    record_system_event(
                        db,
                        level="INFO",
                        category="risk",
                        message="MIS margin caps clamped quantity",
                        correlation_id=correlation_id,
                        details={
                            "order_id": order.id,
                            "old_qty": old_qty,
                            "new_qty": float(new_qty),
                            "cap_trade": cap_trade,
                            "cap_portfolio": cap_portfolio,
                        },
                    )

    # Handle broker-native GTT orders by creating a Zerodha GTT instead of a
    # regular/AMO order. We currently support single-leg LIMIT GTTs
    # for equity; more advanced patterns (OCO, SL GTT) can be layered
    # on later.
    if order.gtt and not order.synthetic_gtt:
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
        order.sent_at = now_utc
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
            if broker_name == "angelone":
                if angelone_token is None:
                    raise RuntimeError("Missing AngelOne symbol token.")
                ltp = client.get_ltp(  # type: ignore[call-arg]
                    exchange=exchange_u,
                    tradingsymbol=broker_tradingsymbol,
                    symboltoken=angelone_token,
                )
            else:
                ltp = client.get_ltp(exchange=exchange, tradingsymbol=tradingsymbol)  # type: ignore[call-arg]
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

    if broker_name == "angelone":
        ordertype_map = {
            "MARKET": "MARKET",
            "LIMIT": "LIMIT",
            "SL": "STOPLOSS_LIMIT",
            "SL-M": "STOPLOSS_MARKET",
        }
        smart_order_type = ordertype_map.get(order.order_type.upper(), "MARKET")
        # SmartAPI product types differ from Zerodha naming.
        # Map internal product labels to SmartAPI equivalents.
        product_raw = (order.product or "CNC").strip().upper()
        product_map = {
            "CNC": "DELIVERY",
            "MIS": "INTRADAY",
            "NRML": "MARGIN",
        }
        producttype = product_map.get(product_raw, "DELIVERY")

        price: float | None = None
        if order.order_type in {"LIMIT", "SL"}:
            if order.price is None or order.price <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Price must be positive for LIMIT/SL orders.",
                )
            price = float(order.price)
        trigger_price: float | None = None
        if order.order_type in {"SL", "SL-M"} and order.trigger_price is not None:
            trigger_price = float(order.trigger_price)

        try:
            if angelone_token is None:
                raise RuntimeError("Missing AngelOne symbol token.")
            result = client.place_order(  # type: ignore[call-arg]
                exchange=exchange_u,
                tradingsymbol=broker_tradingsymbol,
                symboltoken=angelone_token,
                transactiontype=order.side,
                quantity=int(order.qty),
                ordertype=smart_order_type,
                producttype=producttype,
                price=price,
                triggerprice=trigger_price,
            )
        except Exception as exc:
            message = str(exc)
            order.status = "FAILED"
            order.error_message = message
            db.add(order)
            db.commit()
            db.refresh(order)
            record_system_event(
                db,
                level="ERROR",
                category="order",
                message="AngelOne order placement failed",
                correlation_id=correlation_id,
                details={
                    "order_id": order.id,
                    "broker_name": broker_name,
                    "symbol": order.symbol,
                    "error": message,
                },
            )
            _release_execution_policy_inflight()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"AngelOne order placement failed: {message}",
            ) from exc

        order.broker_order_id = result.order_id
        order.status = "SENT"
        order.sent_at = now_utc
        order.error_message = None
        db.add(order)
        db.commit()
        db.refresh(order)
        record_system_event(
            db,
            level="INFO",
            category="order",
            message="Order sent to angelone",
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
        if execution_policy_apply and execution_policy_key is not None:
            key = execution_policy_key
            interval_min = int(
                execution_policy_interval_min
                or interval_minutes_for_order(order, None)
            )
            state = get_or_create_execution_state(
                db,
                key=key,
                now_utc=now_utc,
                interval_minutes=interval_min,
                lock=True,
            )
            interval_eff, interval_src = resolve_interval_for_order(order, state)
            if interval_eff and int(state.interval_minutes or 0) != int(interval_eff):
                state.interval_minutes = int(interval_eff)
            if interval_src and str(getattr(state, "interval_source", "") or "") != str(
                interval_src
            ):
                state.interval_source = str(interval_src)
            price_for_pnl = float(order.price) if order.price else None
            apply_post_trade_updates_on_execution_unified(
                ExecutionPolicyParams(enabled=True),
                state,
                now_utc=now_utc,
                side=str(order.side),
                qty=float(order.qty or 0.0),
                exec_price=price_for_pnl,
            )
            if (
                getattr(state, "inflight_order_id", None) is not None
                and int(state.inflight_order_id) == int(order.id)
            ):  # type: ignore[arg-type]
                state.inflight_order_id = None
                state.inflight_started_at = None
                state.inflight_expires_at = None
            db.add(state)
            db.commit()
        _sync_for_managed_risk()
        return order

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

        extra: dict[str, object] = {}
        if broker_name == "zerodha" and getattr(order, "portfolio_group_id", None):
            # Zerodha supports an optional `tag` field for client-side attribution.
            # Keep it short and alphanumeric to satisfy broker constraints.
            gid = int(order.portfolio_group_id)  # type: ignore[arg-type]
            extra["tag"] = f"STPF{gid}"

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
            **extra,
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
                _release_execution_policy_inflight()
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
            _release_execution_policy_inflight()
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
        _release_execution_policy_inflight()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Zerodha order placement failed.",
        )

    order.broker_order_id = result.order_id
    if broker_name == "zerodha":
        order.zerodha_order_id = result.order_id
    order.status = "SENT"
    order.sent_at = now_utc
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
    if execution_policy_apply and execution_policy_key is not None:
        key = execution_policy_key
        interval_min = int(
            execution_policy_interval_min
            or interval_minutes_for_order(order, None)
        )
        state = get_or_create_execution_state(
            db,
            key=key,
            now_utc=now_utc,
            interval_minutes=interval_min,
            lock=True,
        )
        interval_eff, interval_src = resolve_interval_for_order(order, state)
        if interval_eff and int(state.interval_minutes or 0) != int(interval_eff):
            state.interval_minutes = int(interval_eff)
        if interval_src and str(getattr(state, "interval_source", "") or "") != str(
            interval_src
        ):
            state.interval_source = str(interval_src)
        price_for_pnl = float(order.price) if order.price else None
        apply_post_trade_updates_on_execution_unified(
            ExecutionPolicyParams(enabled=True),
            state,
            now_utc=now_utc,
            side=str(order.side),
            qty=float(order.qty or 0.0),
            exec_price=price_for_pnl,
        )
        if (
            getattr(state, "inflight_order_id", None) is not None
            and int(state.inflight_order_id) == int(order.id)
        ):  # type: ignore[arg-type]
            state.inflight_order_id = None
            state.inflight_started_at = None
            state.inflight_expires_at = None
        db.add(state)
        db.commit()
    _sync_for_managed_risk()
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


@router.post("/{order_id}/move-to-waiting", response_model=OrderRead)
def move_order_to_waiting_queue(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Order:
    """Create a new manual WAITING order cloned from an existing order.

    This is a "requeue" operation:
    - The original order stays as immutable history (FAILED/REJECTED_RISK/etc).
    - A new order row is created with mode=MANUAL, status=WAITING so it appears
      in the Waiting Queue for editing/execution.
    """

    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if order.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    if order.simulated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Simulated/PAPER orders cannot be moved to the manual queue.",
        )

    broker_order_id = getattr(order, "broker_order_id", None) or getattr(
        order, "zerodha_order_id", None
    )
    if broker_order_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order already has a broker order id; cannot move to waiting queue.",
        )

    status_u = str(getattr(order, "status", "") or "").strip().upper()
    if status_u in {"SENT", "OPEN", "EXECUTED", "PARTIALLY_EXECUTED"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order status {status_u} cannot be moved to waiting queue.",
        )

    if status_u not in {"WAITING", "FAILED", "REJECTED_RISK", "CANCELLED"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Only WAITING/FAILED/REJECTED_RISK/CANCELLED orders can be requeued; "
                f"got {status_u}."
            ),
        )

    from app.services.orders import requeue_order_to_waiting

    queue_order = requeue_order_to_waiting(db, source=order)

    correlation_id = getattr(request.state, "correlation_id", None)
    # Mark the original order as requeued so the UI does not keep offering the
    # action on the same row. (The user can requeue again from the latest row.)
    suffix = f"Requeued to Waiting Queue as order #{int(queue_order.id)}."
    if suffix not in (order.error_message or ""):
        base = (order.error_message or "").strip()
        order.error_message = f"{base} {suffix}".strip() if base else suffix
        db.add(order)
        db.commit()
        db.refresh(order)

    record_system_event(
        db,
        level="INFO",
        category="order",
        message="Order requeued to waiting queue",
        correlation_id=correlation_id,
        details={
            "source_order_id": int(order.id),
            "queue_order_id": int(queue_order.id),
            "symbol": queue_order.symbol,
            "status": status_u,
        },
    )
    return queue_order


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
    if broker == "zerodha":
        from app.services.order_sync import sync_order_statuses

        updated = sync_order_statuses(db, client, user_id=user.id)  # type: ignore[arg-type]
    elif broker == "angelone":
        from app.services.order_sync_angelone import sync_order_statuses_angelone

        updated = sync_order_statuses_angelone(db, client, user_id=user.id)  # type: ignore[arg-type]
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order sync not implemented for broker: {broker}",
        )
    return {"updated": updated}


__all__ = ["router"]
