from __future__ import annotations

from datetime import UTC, datetime
from threading import Event, Lock, Thread

from app.db.session import SessionLocal
from app.services.deployment_jobs import requeue_stale_running_jobs, sweep_stale_locks

_sweeper_started = False
_sweeper_stop_event = Event()
_sweeper_lock = Lock()


def sweep_once(*, running_ttl_seconds: int = 60) -> dict[str, int]:
    with SessionLocal() as db:
        now = datetime.now(UTC)
        requeued = requeue_stale_running_jobs(
            db,
            now=now,
            running_ttl_seconds=running_ttl_seconds,
        )
        unlocked = sweep_stale_locks(db, now=now)
        db.commit()
        return {"requeued_jobs": int(requeued), "cleared_locks": int(unlocked)}


def _sweeper_loop() -> None:  # pragma: no cover - background thread
    while not _sweeper_stop_event.is_set():
        try:
            sweep_once()
        except Exception:
            pass
        _sweeper_stop_event.wait(timeout=5.0)


def schedule_deployment_sweeper() -> None:
    global _sweeper_started
    with _sweeper_lock:
        if _sweeper_started:
            return
        _sweeper_started = True

    thread = Thread(target=_sweeper_loop, name="deployment-sweeper", daemon=True)
    thread.start()


__all__ = ["schedule_deployment_sweeper", "sweep_once"]
