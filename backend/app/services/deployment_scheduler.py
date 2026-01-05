from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Event, Lock, Thread
from typing import Any, Iterator

from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings, get_settings
from app.core.market_hours import IST_OFFSET, resolve_market_session
from app.db.session import SessionLocal
from app.models import GroupMember, StrategyDeployment, StrategyDeploymentBarCursor
from app.services.deployment_jobs import enqueue_job
from app.services.market_data import load_series

INTRADAY_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
}

DEFAULT_LATE_TOLERANCE_SECONDS = 5
DEFAULT_MAX_BACKFILL_BARS = 100

_scheduler_started = False
_scheduler_stop_event = Event()
_scheduler_lock = Lock()


def now_ist_naive(now_utc: datetime | None = None) -> datetime:
    base = now_utc or datetime.now(UTC)
    return (base + IST_OFFSET).replace(tzinfo=None)


def ist_naive_to_utc(dt_ist: datetime) -> datetime:
    return (dt_ist - IST_OFFSET).replace(tzinfo=UTC)


def utc_to_ist_naive(dt_utc: datetime) -> datetime:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=UTC)
    return (dt_utc.astimezone(UTC) + IST_OFFSET).replace(tzinfo=None)


def _floor_to_minute(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0)


def latest_closed_bar_end_ist(
    *,
    now_ist: datetime,
    timeframe: str,
    tolerance_seconds: int = DEFAULT_LATE_TOLERANCE_SECONDS,
) -> datetime | None:
    """Return latest bar end (IST-naive) considered closed for timeframe."""

    minutes = INTRADAY_MINUTES.get(timeframe)
    if minutes is None:
        return None
    dt = now_ist - timedelta(seconds=tolerance_seconds)
    floored = _floor_to_minute(dt)
    if minutes == 1:
        return floored
    minute_bucket = (floored.minute // minutes) * minutes
    return floored.replace(minute=0) + timedelta(minutes=minute_bucket)


def iter_missing_bar_ends(
    *,
    last_emitted_end_ist: datetime | None,
    latest_closed_end_ist: datetime,
    timeframe: str,
    max_backfill: int = DEFAULT_MAX_BACKFILL_BARS,
) -> Iterator[datetime]:
    minutes = INTRADAY_MINUTES.get(timeframe)
    if minutes is None:
        return

    delta = timedelta(minutes=minutes)
    if last_emitted_end_ist is None:
        yield latest_closed_end_ist
        return

    next_end = last_emitted_end_ist + delta
    count = 0
    while next_end <= latest_closed_end_ist:
        yield next_end
        next_end = next_end + delta
        count += 1
        if count >= max_backfill:
            return


def _load_deployment_payload(dep: StrategyDeployment) -> dict[str, Any]:
    try:
        return json.loads(dep.config_json or "{}")
    except Exception:
        return {}


def resolve_deployment_symbols(
    db: Session, dep: StrategyDeployment
) -> list[dict[str, str]]:
    payload = _load_deployment_payload(dep)
    universe = payload.get("universe") or {}
    target_kind = (universe.get("target_kind") or dep.target_kind or "SYMBOL").strip()

    if target_kind == "SYMBOL":
        symbols = universe.get("symbols") or []
        if symbols:
            s0 = symbols[0] or {}
            exchange = str(s0.get("exchange") or dep.exchange or "NSE").upper()
            symbol = str(s0.get("symbol") or dep.symbol or "").upper()
            if symbol:
                return [{"exchange": exchange, "symbol": symbol}]
        if dep.symbol:
            return [
                {
                    "exchange": str(dep.exchange or "NSE").upper(),
                    "symbol": dep.symbol,
                }
            ]
        return []

    group_id = universe.get("group_id") or dep.group_id
    if group_id:
        members: list[GroupMember] = (
            db.query(GroupMember).filter(GroupMember.group_id == int(group_id)).all()
        )
        out: list[dict[str, str]] = []
        for m in members:
            out.append(
                {
                    "exchange": str(m.exchange or "NSE").upper(),
                    "symbol": str(m.symbol).upper(),
                }
            )
        return out

    symbols = universe.get("symbols") or []
    out = []
    for s in symbols:
        if not isinstance(s, dict):
            continue
        sym = str(s.get("symbol") or "").upper()
        if not sym:
            continue
        out.append({"exchange": str(s.get("exchange") or "NSE").upper(), "symbol": sym})
    return out


@dataclass(frozen=True)
class EnqueueResult:
    jobs_created: int = 0
    jobs_deduped: int = 0


def enqueue_due_jobs_once(
    db: Session,
    settings: Settings,
    *,
    now_utc: datetime | None = None,
    tolerance_seconds: int = DEFAULT_LATE_TOLERANCE_SECONDS,
    max_backfill: int = DEFAULT_MAX_BACKFILL_BARS,
    prefetch_candles: bool = True,
) -> EnqueueResult:
    """Scan enabled deployments and enqueue due BAR_CLOSED / proxy/window jobs."""

    now_u = now_utc or datetime.now(UTC)
    now_i = now_ist_naive(now_u)

    deps: list[StrategyDeployment] = (
        db.query(StrategyDeployment)
        .options(joinedload(StrategyDeployment.state))
        .filter(StrategyDeployment.enabled.is_(True))
        .all()
    )
    created = 0
    deduped = 0

    for dep in deps:
        payload = _load_deployment_payload(dep)
        cfg = payload.get("config") or {}
        tf = (cfg.get("timeframe") or dep.timeframe or "1d").strip()
        status = str(getattr(dep.state, "status", None) or "STOPPED").upper()
        product = str(cfg.get("product") or dep.product or "CNC").upper()

        symbols = resolve_deployment_symbols(db, dep)
        if not symbols:
            continue

        if tf in INTRADAY_MINUTES and status == "RUNNING":
            for sym in symbols:
                exchange = sym["exchange"]
                symbol = sym["symbol"]

                session = resolve_market_session(
                    db, day=now_i.date(), exchange=exchange
                )
                if not session.is_trading_time(now_i):
                    continue

                latest_end_ist = latest_closed_bar_end_ist(
                    now_ist=now_i,
                    timeframe=tf,
                    tolerance_seconds=tolerance_seconds,
                )
                if latest_end_ist is None:
                    continue
                if (
                    session.open_time is None
                    or session.close_time is None
                    or latest_end_ist.time() <= session.open_time
                    or latest_end_ist.time() > session.close_time
                ):
                    continue

                cursor: StrategyDeploymentBarCursor | None = (
                    db.query(StrategyDeploymentBarCursor)
                    .filter(
                        StrategyDeploymentBarCursor.deployment_id == dep.id,
                        StrategyDeploymentBarCursor.exchange == exchange,
                        StrategyDeploymentBarCursor.symbol == symbol,
                        StrategyDeploymentBarCursor.timeframe == tf,
                    )
                    .one_or_none()
                )
                last_emitted_ist = (
                    utc_to_ist_naive(cursor.last_emitted_bar_end_ts)
                    if cursor and cursor.last_emitted_bar_end_ts
                    else None
                )
                if (
                    last_emitted_ist is not None
                    and last_emitted_ist.date() != now_i.date()
                ):
                    # Avoid overnight churn: restart bar cursors at the current session.
                    # We intentionally do not backfill out-of-session bars.
                    assert session.open_time is not None
                    last_emitted_ist = datetime.combine(now_i.date(), session.open_time)

                for bar_end_ist in iter_missing_bar_ends(
                    last_emitted_end_ist=last_emitted_ist,
                    latest_closed_end_ist=latest_end_ist,
                    timeframe=tf,
                    max_backfill=max_backfill,
                ):
                    if (
                        session.open_time is None
                        or session.close_time is None
                        or bar_end_ist.time() <= session.open_time
                        or bar_end_ist.time() > session.close_time
                    ):
                        continue
                    if prefetch_candles:
                        # Best-effort prefetch (DB-first, broker fallback) for the
                        # minimal window around this bar.
                        try:
                            start = bar_end_ist - timedelta(
                                minutes=INTRADAY_MINUTES[tf] * 2
                            )
                            end = bar_end_ist
                            load_series(
                                db,
                                settings,
                                symbol=symbol,
                                exchange=exchange,
                                timeframe=tf,  # type: ignore[arg-type]
                                start=start,
                                end=end,
                                allow_fetch=True,
                            )
                        except Exception:
                            pass

                    bar_end_utc = ist_naive_to_utc(bar_end_ist)
                    dedupe_key = (
                        f"DEP:{dep.id}:BAR_CLOSED:{tf}:{exchange}:{symbol}:"
                        f"{bar_end_utc.isoformat()}"
                    )
                    job = enqueue_job(
                        db,
                        deployment_id=dep.id,
                        owner_id=dep.owner_id,
                        kind="BAR_CLOSED",
                        dedupe_key=dedupe_key,
                        scheduled_for=bar_end_utc,
                        payload={
                            "kind": "BAR_CLOSED",
                            "deployment_id": dep.id,
                            "timeframe": tf,
                            "exchange": exchange,
                            "symbol": symbol,
                            "bar_end_ist": bar_end_ist.isoformat(),
                            "bar_end_utc": bar_end_utc.isoformat(),
                        },
                    )
                    if job is None:
                        deduped += 1
                    else:
                        created += 1

                    if cursor is None:
                        cursor = StrategyDeploymentBarCursor(
                            deployment_id=dep.id,
                            exchange=exchange,
                            symbol=symbol,
                            timeframe=tf,
                            last_emitted_bar_end_ts=bar_end_utc,
                        )
                        db.add(cursor)
                    else:
                        cursor.last_emitted_bar_end_ts = bar_end_utc
                        db.add(cursor)

        if tf == "1d":
            daily = cfg.get("daily_via_intraday") or {
                "enabled": True,
                "base_timeframe": "5m",
            }
            enabled = bool(daily.get("enabled", True))
            if not enabled:
                continue

            base_tf = str(daily.get("base_timeframe") or "5m")
            if base_tf in INTRADAY_MINUTES and status == "RUNNING":
                for sym in symbols:
                    exchange = sym["exchange"]
                    symbol = sym["symbol"]

                    session = resolve_market_session(
                        db, day=now_i.date(), exchange=exchange
                    )
                    if not session.is_trading_time(now_i):
                        continue

                    latest_end_ist = latest_closed_bar_end_ist(
                        now_ist=now_i,
                        timeframe=base_tf,
                        tolerance_seconds=tolerance_seconds,
                    )
                    if latest_end_ist is None:
                        continue
                    if (
                        session.open_time is None
                        or session.close_time is None
                        or latest_end_ist.time() <= session.open_time
                        or latest_end_ist.time() > session.close_time
                    ):
                        continue

                    cursor: StrategyDeploymentBarCursor | None = (
                        db.query(StrategyDeploymentBarCursor)
                        .filter(
                            StrategyDeploymentBarCursor.deployment_id == dep.id,
                            StrategyDeploymentBarCursor.exchange == exchange,
                            StrategyDeploymentBarCursor.symbol == symbol,
                            StrategyDeploymentBarCursor.timeframe == base_tf,
                        )
                        .one_or_none()
                    )
                    last_emitted_ist = (
                        utc_to_ist_naive(cursor.last_emitted_bar_end_ts)
                        if cursor and cursor.last_emitted_bar_end_ts
                        else None
                    )
                    if (
                        last_emitted_ist is not None
                        and last_emitted_ist.date() != now_i.date()
                    ):
                        assert session.open_time is not None
                        last_emitted_ist = datetime.combine(
                            now_i.date(), session.open_time
                        )

                    for bar_end_ist in iter_missing_bar_ends(
                        last_emitted_end_ist=last_emitted_ist,
                        latest_closed_end_ist=latest_end_ist,
                        timeframe=base_tf,
                        max_backfill=max_backfill,
                    ):
                        if (
                            session.open_time is None
                            or session.close_time is None
                            or bar_end_ist.time() <= session.open_time
                            or bar_end_ist.time() > session.close_time
                        ):
                            continue
                        bar_end_utc = ist_naive_to_utc(bar_end_ist)
                        dedupe_key = (
                            f"DEP:{dep.id}:BAR_CLOSED:{base_tf}:{exchange}:{symbol}:"
                            f"{bar_end_utc.isoformat()}"
                        )
                        job = enqueue_job(
                            db,
                            deployment_id=dep.id,
                            owner_id=dep.owner_id,
                            kind="BAR_CLOSED",
                            dedupe_key=dedupe_key,
                            scheduled_for=bar_end_utc,
                            payload={
                                "kind": "BAR_CLOSED",
                                "deployment_id": dep.id,
                                "timeframe": base_tf,
                                "exchange": exchange,
                                "symbol": symbol,
                                "purpose": "RISK",
                                "bar_end_ist": bar_end_ist.isoformat(),
                                "bar_end_utc": bar_end_utc.isoformat(),
                            },
                        )
                        if job is None:
                            deduped += 1
                        else:
                            created += 1
                        if cursor is None:
                            cursor = StrategyDeploymentBarCursor(
                                deployment_id=dep.id,
                                exchange=exchange,
                                symbol=symbol,
                                timeframe=base_tf,
                                last_emitted_bar_end_ts=bar_end_utc,
                            )
                            db.add(cursor)
                        else:
                            cursor.last_emitted_bar_end_ts = bar_end_utc
                            db.add(cursor)

            primary_exchange = symbols[0]["exchange"]
            session = resolve_market_session(
                db, day=now_i.date(), exchange=primary_exchange
            )
            if not session.is_trading_time(now_i) or status != "RUNNING":
                continue
            if session.proxy_close_time is None or session.open_time is None:
                continue

            proxy_dt_ist = datetime.combine(now_i.date(), session.proxy_close_time)
            close_dt_ist = datetime.combine(
                now_i.date(), session.close_time  # type: ignore[arg-type]
            )
            if (
                now_i >= (proxy_dt_ist + timedelta(seconds=tolerance_seconds))
                and now_i <= close_dt_ist
            ):
                proxy_dt_utc = ist_naive_to_utc(proxy_dt_ist)
                job = enqueue_job(
                    db,
                    deployment_id=dep.id,
                    owner_id=dep.owner_id,
                    kind="DAILY_PROXY_CLOSED",
                    dedupe_key=f"DEP:{dep.id}:DAILY_PROXY_CLOSED:{proxy_dt_utc.date().isoformat()}",
                    scheduled_for=proxy_dt_utc,
                    payload={
                        "kind": "DAILY_PROXY_CLOSED",
                        "deployment_id": dep.id,
                        "proxy_close_ist": proxy_dt_ist.isoformat(),
                        "proxy_close_utc": proxy_dt_utc.isoformat(),
                    },
                )
                if job is None:
                    deduped += 1
                else:
                    created += 1

            sell_dt_ist = datetime.combine(now_i.date(), session.open_time)
            if (
                now_i >= (sell_dt_ist + timedelta(seconds=tolerance_seconds))
                and now_i <= close_dt_ist
            ):
                sell_dt_utc = ist_naive_to_utc(sell_dt_ist)
                job = enqueue_job(
                    db,
                    deployment_id=dep.id,
                    owner_id=dep.owner_id,
                    kind="WINDOW",
                    dedupe_key=f"DEP:{dep.id}:WINDOW:SELL_OPEN:{sell_dt_utc.date().isoformat()}",
                    scheduled_for=sell_dt_utc,
                    payload={
                        "kind": "WINDOW",
                        "window": "SELL_OPEN",
                        "deployment_id": dep.id,
                        "window_ist": sell_dt_ist.isoformat(),
                        "window_utc": sell_dt_utc.isoformat(),
                    },
                )
                if job is None:
                    deduped += 1
                else:
                    created += 1

            buy_dt_ist = datetime.combine(now_i.date(), session.proxy_close_time)
            if (
                now_i >= (buy_dt_ist + timedelta(seconds=tolerance_seconds))
                and now_i <= close_dt_ist
            ):
                buy_dt_utc = ist_naive_to_utc(buy_dt_ist)
                job = enqueue_job(
                    db,
                    deployment_id=dep.id,
                    owner_id=dep.owner_id,
                    kind="WINDOW",
                    dedupe_key=f"DEP:{dep.id}:WINDOW:BUY_CLOSE:{buy_dt_utc.date().isoformat()}",
                    scheduled_for=buy_dt_utc,
                    payload={
                        "kind": "WINDOW",
                        "window": "BUY_CLOSE",
                        "deployment_id": dep.id,
                        "window_ist": buy_dt_ist.isoformat(),
                        "window_utc": buy_dt_utc.isoformat(),
                    },
                )
                if job is None:
                    deduped += 1
                else:
                    created += 1

        # Safety invariant: MIS square-off runs even when a deployment is PAUSED.
        if product == "MIS" and status in {"RUNNING", "PAUSED"}:
            primary_exchange = symbols[0]["exchange"]
            session = resolve_market_session(
                db, day=now_i.date(), exchange=primary_exchange
            )
            if not session.is_trading_time(now_i):
                continue
            if session.proxy_close_time is None or session.close_time is None:
                continue
            buy_dt_ist = datetime.combine(now_i.date(), session.proxy_close_time)
            close_dt_ist = datetime.combine(
                now_i.date(), session.close_time  # type: ignore[arg-type]
            )
            if (
                now_i >= (buy_dt_ist + timedelta(seconds=tolerance_seconds))
                and now_i <= close_dt_ist
            ):
                buy_dt_utc = ist_naive_to_utc(buy_dt_ist)
                job = enqueue_job(
                    db,
                    deployment_id=dep.id,
                    owner_id=dep.owner_id,
                    kind="WINDOW",
                    dedupe_key=(
                        f"DEP:{dep.id}:WINDOW:MIS_FLATTEN:{buy_dt_utc.date().isoformat()}"
                    ),
                    scheduled_for=buy_dt_utc,
                    payload={
                        "kind": "WINDOW",
                        "window": "MIS_FLATTEN",
                        "deployment_id": dep.id,
                        "window_ist": buy_dt_ist.isoformat(),
                        "window_utc": buy_dt_utc.isoformat(),
                    },
                )
                if job is None:
                    deduped += 1
                else:
                    created += 1

    return EnqueueResult(jobs_created=created, jobs_deduped=deduped)


def _scheduler_loop() -> None:  # pragma: no cover - background thread
    settings = get_settings()
    while not _scheduler_stop_event.is_set():
        with SessionLocal() as db:
            try:
                enqueue_due_jobs_once(db, settings)
                db.commit()
            except Exception:
                db.rollback()
        _scheduler_stop_event.wait(timeout=1.0)


def schedule_deployment_scheduler() -> None:
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True

    thread = Thread(target=_scheduler_loop, name="deployment-scheduler", daemon=True)
    thread.start()


__all__ = [
    "DEFAULT_LATE_TOLERANCE_SECONDS",
    "DEFAULT_MAX_BACKFILL_BARS",
    "EnqueueResult",
    "enqueue_due_jobs_once",
    "ist_naive_to_utc",
    "iter_missing_bar_ends",
    "latest_closed_bar_end_ist",
    "now_ist_naive",
    "schedule_deployment_scheduler",
    "utc_to_ist_naive",
]
