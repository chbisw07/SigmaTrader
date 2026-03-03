from __future__ import annotations

import logging
from datetime import UTC, datetime
from threading import Event, Thread

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_scheduler_started = False
_scheduler_stop_event = Event()


def _now_utc() -> datetime:
    return datetime.now(UTC)


def process_no_trade_deferred_dispatch_once() -> int:
    """DEPRECATED (no-op): legacy NO_TRADE auto-resume worker.

    SigmaTrader now treats time windows as an AUTO pause mechanism: auto
    executions are converted into MANUAL queue items and require explicit
    user action to execute. This avoids surprising delayed executions and
    provides a clear "pause AUTO" kill switch.
    """

    settings = get_settings()
    if not getattr(settings, "no_trade_deferred_dispatch_enabled", True):
        return 0
    return 0


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
    settings = get_settings()
    if not getattr(settings, "no_trade_deferred_dispatch_enabled", True):
        return
    if _scheduler_started:
        return
    _scheduler_started = True
    thread = Thread(target=_loop, name="no-trade-deferred", daemon=True)
    thread.start()


__all__ = [
    "process_no_trade_deferred_dispatch_once",
    "schedule_no_trade_deferred_dispatch",
]
