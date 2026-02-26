from __future__ import annotations

import logging
from datetime import UTC, datetime
from threading import Event, Thread

from fastapi import HTTPException

from app.core.config import get_settings
from app.core.market_hours import is_market_open_now
from app.db.session import SessionLocal
from app.models import Order

logger = logging.getLogger(__name__)

_scheduler_started = False
_scheduler_stop_event = Event()


def _now_utc() -> datetime:
    return datetime.now(UTC)


def process_no_trade_deferred_dispatch_once() -> int:
    """Retry AUTO orders that were deferred by a NO_TRADE window.

    Orders are deferred by setting:
    - status=WAITING
    - mode=AUTO
    - armed_at=<defer_until_utc>
    - error_message contains "NO_TRADE"
    """

    settings = get_settings()
    if not getattr(settings, "no_trade_deferred_dispatch_enabled", True):
        return 0

    if not is_market_open_now():
        return 0

    max_per_cycle = int(
        getattr(settings, "no_trade_deferred_dispatch_max_per_cycle", 50) or 50
    )
    max_per_cycle = max(1, max_per_cycle)

    from app.api.orders import execute_order_internal

    now = _now_utc()
    processed = 0
    with SessionLocal() as db:
        # Backward-compatible selection:
        # - New behavior: WAITING/AUTO with armed_at=defer_until_utc.
        # - Legacy behavior: WAITING/MANUAL rows created from alerts that contain
        #   a NO_TRADE deferral message but may have armed_at unset.
        due_pred = (Order.armed_at.is_not(None) & (Order.armed_at <= now)) | (
            Order.armed_at.is_(None)
        )
        pending: list[Order] = (
            db.query(Order)
            .filter(
                Order.status == "WAITING",
                Order.simulated.is_(False),
                Order.gtt.is_(False),
                Order.synthetic_gtt.is_(False),
                Order.broker_order_id.is_(None),
                Order.zerodha_order_id.is_(None),
                due_pred,
                (Order.mode == "AUTO")
                | ((Order.mode == "MANUAL") & (Order.alert_id.is_not(None))),
                Order.error_message.is_not(None),
                Order.error_message.like("%NO_TRADE%"),
            )
            .order_by(Order.armed_at.asc(), Order.created_at.asc())
            .limit(max_per_cycle)
            .all()
        )
        if not pending:
            return 0

        for order in pending:
            try:
                execute_order_internal(
                    int(order.id),
                    db=db,
                    settings=settings,
                    correlation_id="no-trade-deferred",
                    auto_dispatch=True,
                )
                processed += 1
            except HTTPException as exc:
                # If execution failed before a status transition, fail the order
                # so we don't spin forever retrying a structurally invalid row.
                try:
                    db.refresh(order)
                    if str(getattr(order, "status", "") or "").strip().upper() == "WAITING":
                        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
                        order.status = "FAILED"
                        order.error_message = detail
                        db.add(order)
                        db.commit()
                except Exception:
                    try:
                        db.rollback()
                    except Exception:
                        pass
                processed += 1
            except Exception as exc:
                logger.info(
                    "Deferred NO_TRADE retry failed",
                    extra={"extra": {"order_id": int(order.id), "error": str(exc)}},
                )
                try:
                    db.refresh(order)
                    if str(getattr(order, "status", "") or "").strip().upper() == "WAITING":
                        order.status = "FAILED"
                        order.error_message = str(exc)
                        db.add(order)
                        db.commit()
                except Exception:
                    try:
                        db.rollback()
                    except Exception:
                        pass
                processed += 1

    return processed


def _loop() -> None:
    settings = get_settings()
    interval = float(getattr(settings, "no_trade_deferred_dispatch_poll_interval_sec", 5) or 5)
    interval = max(1.0, interval)
    while not _scheduler_stop_event.is_set():
        try:
            process_no_trade_deferred_dispatch_once()
        except Exception:
            logger.exception("Deferred NO_TRADE dispatch loop failed.")
        _scheduler_stop_event.wait(timeout=interval)


def schedule_no_trade_deferred_dispatch() -> None:
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True
    thread = Thread(target=_loop, name="no-trade-deferred", daemon=True)
    thread.start()


__all__ = [
    "process_no_trade_deferred_dispatch_once",
    "schedule_no_trade_deferred_dispatch",
]
