from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from threading import Event, Thread

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.clients import AngelOneClient, AngelOneSession, ZerodhaClient
from app.core.config import Settings, get_settings
from app.core.crypto import decrypt_token
from app.core.market_hours import is_market_open_now
from app.db.session import SessionLocal
from app.models import BrokerConnection, Order
from app.services.broker_instruments import resolve_broker_symbol_and_token
from app.services.broker_secrets import get_broker_secret

logger = logging.getLogger(__name__)

_scheduler_started = False
_scheduler_stop_event = Event()


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _get_zerodha_client(
    db: Session,
    settings: Settings,
    *,
    user_id: int,
) -> ZerodhaClient:
    conn = (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.broker_name == "zerodha",
            BrokerConnection.user_id == user_id,
        )
        .order_by(BrokerConnection.updated_at.desc())
        .first()
    )
    if conn is None:
        raise RuntimeError("Zerodha is not connected.")

    api_key = get_broker_secret(db, settings, "zerodha", "api_key", user_id=user_id)
    if not api_key:
        raise RuntimeError("Zerodha API key is not configured.")

    from kiteconnect import KiteConnect  # type: ignore[import]

    access_token = decrypt_token(settings, conn.access_token_encrypted)
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return ZerodhaClient(kite)


def _get_angelone_client(
    db: Session,
    settings: Settings,
    *,
    user_id: int,
) -> AngelOneClient:
    conn = (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.broker_name == "angelone",
            BrokerConnection.user_id == user_id,
        )
        .order_by(BrokerConnection.updated_at.desc())
        .first()
    )
    if conn is None:
        raise RuntimeError("AngelOne is not connected.")

    api_key = get_broker_secret(db, settings, "angelone", "api_key", user_id=user_id)
    if not api_key:
        raise RuntimeError("SmartAPI API key is not configured.")

    raw = decrypt_token(settings, conn.access_token_encrypted)
    parsed = json.loads(raw) if raw else {}
    jwt = str(parsed.get("jwt_token") or "")
    if not jwt:
        raise RuntimeError("AngelOne session is missing jwt_token.")

    session = AngelOneSession(
        jwt_token=jwt,
        refresh_token=str(parsed.get("refresh_token") or "") or None,
        feed_token=str(parsed.get("feed_token") or "") or None,
        client_code=str(parsed.get("client_code") or "") or None,
    )
    return AngelOneClient(api_key=api_key, session=session)


def _fetch_ltp_from_zerodha(
    db: Session,
    settings: Settings,
    *,
    order: Order,
) -> float:
    exchange = (order.exchange or "NSE").strip().upper()
    symbol = order.symbol.strip().upper()
    if not order.user_id:
        raise RuntimeError("Order is missing user_id.")
    client = _get_zerodha_client(db, settings, user_id=order.user_id)
    return float(client.get_ltp(exchange=exchange, tradingsymbol=symbol))


def _fetch_ltp_from_destination_broker(
    db: Session,
    settings: Settings,
    *,
    order: Order,
) -> float:
    exchange = (order.exchange or "NSE").strip().upper()
    symbol = order.symbol.strip().upper()
    broker = (order.broker_name or "zerodha").strip().lower()
    if not order.user_id:
        raise RuntimeError("Order is missing user_id.")

    if broker == "zerodha":
        client = _get_zerodha_client(db, settings, user_id=order.user_id)
        return float(client.get_ltp(exchange=exchange, tradingsymbol=symbol))

    if broker == "angelone":
        resolved = resolve_broker_symbol_and_token(
            db,
            broker_name="angelone",
            exchange=exchange,
            symbol=symbol,
        )
        if resolved is None:
            raise RuntimeError(
                f"AngelOne instrument mapping missing for {exchange}:{symbol}."
            )
        broker_symbol, token = resolved
        client = _get_angelone_client(db, settings, user_id=order.user_id)
        return float(
            client.get_ltp(
                exchange=exchange,
                tradingsymbol=broker_symbol,
                symboltoken=token,
            )
        )

    raise RuntimeError(f"LTP not supported for broker: {broker}")


def _should_trigger(op: str, *, ltp: float, trigger: float) -> bool:
    if op == ">=":
        return ltp >= trigger
    return ltp <= trigger


def process_synthetic_gtt_once() -> int:
    """Evaluate and trigger pending synthetic GTT orders (best-effort)."""

    settings = get_settings()
    if not getattr(settings, "synthetic_gtt_enabled", True):
        return 0

    if not is_market_open_now():
        return 0

    max_per_cycle = int(getattr(settings, "synthetic_gtt_max_per_cycle", 50) or 50)
    poll_brokers_ltp = bool(getattr(settings, "synthetic_gtt_use_broker_ltp", False))

    from app.api.orders import execute_order_internal

    now = _now_utc()
    triggered = 0
    with SessionLocal() as db:
        pending: list[Order] = (
            db.query(Order)
            .filter(
                Order.synthetic_gtt.is_(True),
                Order.gtt.is_(True),
                Order.status == "WAITING",
                Order.armed_at.is_not(None),
                Order.triggered_at.is_(None),
            )
            .order_by(Order.created_at.asc())
            .limit(max_per_cycle)
            .all()
        )
        if not pending:
            return 0

        for order in pending:
            if order.trigger_price is None or order.trigger_price <= 0:
                continue
            try:
                ltp: float
                if poll_brokers_ltp:
                    try:
                        ltp = _fetch_ltp_from_destination_broker(
                            db,
                            settings,
                            order=order,
                        )
                    except Exception:
                        ltp = _fetch_ltp_from_zerodha(db, settings, order=order)
                else:
                    try:
                        ltp = _fetch_ltp_from_zerodha(db, settings, order=order)
                    except Exception:
                        ltp = _fetch_ltp_from_destination_broker(
                            db,
                            settings,
                            order=order,
                        )

                order.last_checked_at = now
                order.last_seen_price = float(ltp)
                if not order.trigger_operator:
                    trigger = float(order.trigger_price)
                    order.trigger_operator = ">=" if trigger >= float(ltp) else "<="
                db.add(order)
                db.commit()

                op = (order.trigger_operator or "<=").strip()
                if _should_trigger(
                    op,
                    ltp=float(ltp),
                    trigger=float(order.trigger_price),
                ):
                    order.status = "SENDING"
                    order.triggered_at = now
                    db.add(order)
                    db.commit()
                    try:
                        execute_order_internal(
                            order.id,
                            db=db,
                            settings=settings,
                            correlation_id="synthetic-gtt",
                        )
                        triggered += 1
                    except HTTPException as exc:
                        db.refresh(order)
                        if order.status in {"WAITING", "SENDING"}:
                            order.status = "FAILED"
                            order.error_message = (
                                exc.detail
                                if isinstance(exc.detail, str)
                                else str(exc.detail)
                            )
                            db.add(order)
                            db.commit()
            except Exception as exc:
                logger.info(
                    "Synthetic GTT evaluation failed",
                    extra={
                        "extra": {
                            "order_id": order.id,
                            "broker_name": order.broker_name,
                            "symbol": order.symbol,
                            "error": str(exc),
                        }
                    },
                )
                continue

    return triggered


def _loop() -> None:
    settings = get_settings()
    interval = int(getattr(settings, "synthetic_gtt_poll_interval_sec", 15) or 15)
    interval = max(5, interval)
    while not _scheduler_stop_event.is_set():
        try:
            process_synthetic_gtt_once()
        except Exception:
            logger.exception("Synthetic GTT loop failed.")
        _scheduler_stop_event.wait(timeout=interval)


def schedule_synthetic_gtt() -> None:
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True
    thread = Thread(target=_loop, name="synthetic-gtt", daemon=True)
    thread.start()


__all__ = ["schedule_synthetic_gtt", "process_synthetic_gtt_once"]
