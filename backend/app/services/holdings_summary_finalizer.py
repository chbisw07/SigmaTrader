from __future__ import annotations

import os
import sys
from datetime import UTC, date, datetime
from threading import Event, Lock, Thread

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.market_hours import IST_OFFSET
from app.db.session import SessionLocal
from app.models import BrokerConnection, HoldingsSummarySnapshot, User
from app.services.holdings_summary_snapshots import (
    _as_of_date_ist,
    compute_holdings_summary_metrics,
    prev_trading_day,
    upsert_holdings_summary_snapshot,
)
from app.services.system_events import record_system_event

_state_lock = Lock()
_scheduler_started = False
_stop_event = Event()
_state: dict[str, date | None] = {
    "last_run_ist_date": None,
    "last_missed_ist_date": None,
}


def _now_ist_naive() -> datetime:
    return (datetime.now(UTC) + IST_OFFSET).replace(tzinfo=None)


def _time_in_window(now: datetime, *, start_hhmm: tuple[int, int], end_hhmm: tuple[int, int]) -> bool:
    start = now.replace(hour=start_hhmm[0], minute=start_hhmm[1], second=0, microsecond=0)
    end = now.replace(hour=end_hhmm[0], minute=end_hhmm[1], second=0, microsecond=0)
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
    allow_fetch_market_data: bool,
) -> HoldingsSummarySnapshot:
    # Fetch live holdings via the existing API logic (keeps behavior consistent).
    from app.api import positions as positions_api

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
        allow_fetch_market_data=bool(allow_fetch_market_data),
    )
    return upsert_holdings_summary_snapshot(
        db,
        user_id=int(user.id),
        broker_name=broker,
        as_of_date=as_of_date,
        metrics=metrics,
    )


def _finalize_prev_trading_day(
    *,
    settings: Settings,
    mode: str,
    overwrite_existing: bool,
) -> None:
    now_ist = _now_ist_naive()
    today_ist = _as_of_date_ist(datetime.now(UTC))
    if today_ist.weekday() >= 5:
        return  # weekends: do nothing

    target_date = prev_trading_day(today_ist)
    if target_date >= today_ist:
        return

    with SessionLocal() as db:
        user_ids = _get_zerodha_user_ids(db)
        if not user_ids:
            return

        for user_id in user_ids:
            user = db.query(User).filter(User.id == int(user_id)).one_or_none()
            if user is None:
                continue

            existing = (
                db.query(HoldingsSummarySnapshot)
                .filter(
                    HoldingsSummarySnapshot.user_id == int(user.id),
                    HoldingsSummarySnapshot.broker_name == "zerodha",
                    HoldingsSummarySnapshot.as_of_date == target_date,
                )
                .one_or_none()
            )
            if existing is not None and not overwrite_existing:
                continue

            try:
                row = _capture_snapshot_for_user(
                    db,
                    settings,
                    user=user,
                    broker="zerodha",
                    as_of_date=target_date,
                    allow_fetch_market_data=False,
                )
                record_system_event(
                    db,
                    level="INFO",
                    category="holdings_summary_finalizer",
                    message="Holdings summary finalized",
                    details={
                        "mode": mode,
                        "user_id": int(user.id),
                        "broker": "zerodha",
                        "as_of_date": target_date.isoformat(),
                        "snapshot_id": int(row.id),
                        "run_at_ist": now_ist.isoformat(sep=" "),
                    },
                )
            except Exception as exc:
                record_system_event(
                    db,
                    level="ERROR",
                    category="holdings_summary_finalizer",
                    message="Holdings summary finalization failed",
                    details={
                        "mode": mode,
                        "user_id": int(user.id),
                        "broker": "zerodha",
                        "as_of_date": target_date.isoformat(),
                        "error": str(exc),
                    },
                )


def _finalizer_loop() -> None:  # pragma: no cover - background loop
    settings = get_settings()

    # Capture window: run once between 08:30–09:00 IST.
    window_start = (8, 30)
    window_end = (9, 0)
    deadline_hhmm = (9, 15)

    # Startup catch-up: if we boot before 09:15 IST and yesterday's snapshot is
    # missing, capture it once immediately.
    now_ist = _now_ist_naive()
    if now_ist.weekday() < 5:
        deadline = now_ist.replace(
            hour=deadline_hhmm[0], minute=deadline_hhmm[1], second=0, microsecond=0
        )
        if now_ist < deadline:
            _finalize_prev_trading_day(
                settings=settings,
                mode="startup",
                overwrite_existing=False,
            )

    while not _stop_event.is_set():
        now_ist = _now_ist_naive()
        today_ist = _as_of_date_ist(datetime.now(UTC))

        if today_ist.weekday() < 5:
            deadline = now_ist.replace(
                hour=deadline_hhmm[0],
                minute=deadline_hhmm[1],
                second=0,
                microsecond=0,
            )

            should_run = _time_in_window(now_ist, start_hhmm=window_start, end_hhmm=window_end)
            if should_run:
                with _state_lock:
                    if _state.get("last_run_ist_date") == today_ist:
                        should_run = False
                    else:
                        _state["last_run_ist_date"] = today_ist
                        _state["last_missed_ist_date"] = None

            if should_run:
                _finalize_prev_trading_day(
                    settings=settings,
                    mode="window",
                    overwrite_existing=True,
                )
            elif now_ist >= deadline:
                # Missed the safe window: record once per IST day to keep the UI
                # explainable when daily P&L falls back.
                with _state_lock:
                    if _state.get("last_missed_ist_date") != today_ist:
                        _state["last_missed_ist_date"] = today_ist
                        _state["last_run_ist_date"] = _state.get("last_run_ist_date")
                        try:
                            with SessionLocal() as db:
                                record_system_event(
                                    db,
                                    level="WARNING",
                                    category="holdings_summary_finalizer",
                                    message="Holdings summary finalization missed window",
                                    details={
                                        "deadline_ist": f"{deadline_hhmm[0]:02d}:{deadline_hhmm[1]:02d}",
                                        "today_ist": today_ist.isoformat(),
                                    },
                                )
                        except Exception:
                            pass

        _stop_event.wait(timeout=30.0)


def schedule_holdings_summary_finalizer() -> None:
    global _scheduler_started
    if _scheduler_started:
        return
    if "pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST"):
        return
    _scheduler_started = True

    Thread(
        target=_finalizer_loop,
        name="holdings-summary-finalizer",
        daemon=True,
    ).start()


__all__ = ["schedule_holdings_summary_finalizer"]
