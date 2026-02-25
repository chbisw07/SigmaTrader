from __future__ import annotations

import os
import sys
from datetime import UTC, date, datetime, timedelta
from threading import Event, Lock, Thread

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.market_hours import IST_OFFSET, resolve_market_session
from app.db.session import SessionLocal
from app.models import BrokerConnection, User
from app.services.holdings_summary_snapshots import _as_of_date_ist, upsert_holdings_summary_snapshot
from app.services.system_events import record_system_event

_state_lock = Lock()
_scheduler_started = False
_stop_event = Event()
_state: dict[str, date | None] = {
    "last_1530_ist_date": None,
    "last_1700_ist_date": None,
}


def _time_in_window(
    now: datetime,
    *,
    start_hhmm: tuple[int, int],
    window_seconds: int,
) -> bool:
    start = now.replace(
        hour=start_hhmm[0], minute=start_hhmm[1], second=0, microsecond=0
    )
    end = start + timedelta(seconds=window_seconds)
    return start <= now < end


def _get_zerodha_user_ids(db: Session) -> list[int]:
    rows = (
        db.query(BrokerConnection.user_id)
        .filter(BrokerConnection.broker_name == "zerodha")
        .distinct()
        .all()
    )
    return [int(r[0]) for r in rows if r and r[0] is not None]


def _capture_snapshot_for_user(
    db: Session,
    settings: Settings,
    *,
    user: User,
    broker: str,
    as_of_date: date,
) -> None:
    from app.api import positions as positions_api
    from app.services.holdings_summary_snapshots import compute_holdings_summary_metrics

    holdings = positions_api.list_holdings(
        broker_name=broker,
        db=db,
        settings=settings,
        user=user,
    )

    funds_available: float | None = None
    if broker == "zerodha":
        from app.api import zerodha as zerodha_api

        margins = zerodha_api.zerodha_margins(db=db, settings=settings, user=user)
        raw = margins.get("available") if isinstance(margins, dict) else None
        try:
            funds_available = float(raw) if raw is not None else None
        except Exception:
            funds_available = None

    metrics = compute_holdings_summary_metrics(
        holdings=holdings,
        funds_available=funds_available,
        settings=settings,
        db=db,
        allow_fetch_market_data=False,
    )
    upsert_holdings_summary_snapshot(
        db,
        user_id=int(user.id),
        broker_name=broker,
        as_of_date=as_of_date,
        metrics=metrics,
        update_performance_fields=True,
    )


def _is_trading_day(db: Session, *, day: date) -> bool:
    session = resolve_market_session(db, day=day, exchange="NSE")
    return session.is_trading_day()


def _run_capture_for_all_users(*, settings: Settings, as_of_date: date, run_at_ist: datetime) -> None:
    with SessionLocal() as db:
        if not _is_trading_day(db, day=as_of_date):
            return
        user_ids = _get_zerodha_user_ids(db)
        if not user_ids:
            return
        for user_id in user_ids:
            user = db.query(User).filter(User.id == int(user_id)).one_or_none()
            if user is None:
                continue
            try:
                _capture_snapshot_for_user(
                    db,
                    settings,
                    user=user,
                    broker="zerodha",
                    as_of_date=as_of_date,
                )
                record_system_event(
                    db,
                    level="INFO",
                    category="holdings_summary_daily_snapshot",
                    message="Holdings summary snapshot captured",
                    details={
                        "user_id": int(user.id),
                        "broker": "zerodha",
                        "as_of_date": as_of_date.isoformat(),
                        "run_at_ist": run_at_ist.isoformat(sep=" "),
                    },
                )
            except Exception as exc:
                record_system_event(
                    db,
                    level="ERROR",
                    category="holdings_summary_daily_snapshot",
                    message="Holdings summary snapshot capture failed",
                    details={
                        "user_id": int(user.id),
                        "broker": "zerodha",
                        "as_of_date": as_of_date.isoformat(),
                        "error": str(exc),
                    },
                )


def _daily_snapshot_loop() -> None:  # pragma: no cover - background loop
    settings = get_settings()
    window_seconds = 90  # tolerate clock skew / scheduling jitter

    while not _stop_event.is_set():
        now_utc = datetime.now(UTC)
        today_ist = _as_of_date_ist(now_utc)
        now_ist = (now_utc + IST_OFFSET).replace(tzinfo=None)

        if today_ist.weekday() < 5:
            run_1530 = _time_in_window(
                now_ist, start_hhmm=(15, 30), window_seconds=window_seconds
            )
            run_1700 = _time_in_window(
                now_ist, start_hhmm=(17, 0), window_seconds=window_seconds
            )

            if run_1530:
                with _state_lock:
                    if _state.get("last_1530_ist_date") == today_ist:
                        run_1530 = False
                    else:
                        _state["last_1530_ist_date"] = today_ist
                if run_1530:
                    _run_capture_for_all_users(
                        settings=settings, as_of_date=today_ist, run_at_ist=now_ist
                    )

            if run_1700:
                with _state_lock:
                    if _state.get("last_1700_ist_date") == today_ist:
                        run_1700 = False
                    else:
                        _state["last_1700_ist_date"] = today_ist
                if run_1700:
                    # This overwrites the 15:30 snapshot for the same IST day.
                    _run_capture_for_all_users(
                        settings=settings, as_of_date=today_ist, run_at_ist=now_ist
                    )

        _stop_event.wait(timeout=20.0)


def schedule_holdings_summary_daily_snapshots() -> None:
    global _scheduler_started
    if _scheduler_started:
        return
    if "pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST"):
        return
    _scheduler_started = True

    Thread(
        target=_daily_snapshot_loop,
        name="holdings-summary-daily-snapshots",
        daemon=True,
    ).start()


__all__ = ["schedule_holdings_summary_daily_snapshots"]
