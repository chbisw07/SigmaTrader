from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from threading import Event, Lock, Thread
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.db.session import SessionLocal
from app.models import StrategyDeployment, StrategyDeploymentJob
from app.services.deployment_jobs import (
    acquire_deployment_lock,
    claim_next_job,
    mark_job_done,
    mark_job_error,
    record_action,
    release_deployment_lock,
)

logger = logging.getLogger(__name__)

_worker_started = False
_worker_stop_event = Event()
_worker_lock = Lock()


def _json_load(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        val = json.loads(raw)
    except Exception:
        return {}
    return val if isinstance(val, dict) else {}


def _compute_next_eval(
    dep: StrategyDeployment,
    job: StrategyDeploymentJob,
) -> datetime | None:
    payload = _json_load(dep.config_json)
    cfg = payload.get("config") or {}
    tf = str(cfg.get("timeframe") or dep.timeframe or "1d")
    kind = job.kind
    sched = job.scheduled_for
    if sched is None:
        return None
    if kind == "BAR_CLOSED":
        minutes = {
            "1m": 1,
            "5m": 5,
            "15m": 15,
            "30m": 30,
            "1h": 60,
        }.get(tf)
        if minutes is None:
            return None
        return sched + timedelta(minutes=minutes)
    # DAILY_PROXY_CLOSED/WINDOW: schedule next day same time (holiday/weekend handling
    # is intentionally out of scope for the job queue MVP).
    return sched + timedelta(days=1)


def execute_job_once(
    db: Session,
    *,
    worker_id: str,
    now: datetime | None = None,
) -> bool:
    """Claim and execute a single job; returns True when work was done."""

    ts = now or datetime.now(UTC)
    claim = claim_next_job(db, worker_id=worker_id, now=ts)
    if claim is None:
        return False
    job = claim.job

    got_lock = acquire_deployment_lock(
        db,
        deployment_id=job.deployment_id,
        worker_id=worker_id,
        now=ts,
        ttl_seconds=30,
    )
    if not got_lock:
        mark_job_error(db, job=job, error="Deployment is locked.", now=ts)
        db.commit()
        return True

    dep = (
        db.query(StrategyDeployment)
        .options(joinedload(StrategyDeployment.state))
        .filter(StrategyDeployment.id == job.deployment_id)
        .one_or_none()
    )
    if dep is None or dep.enabled is not True:
        mark_job_done(db, job=job, now=ts)
        release_deployment_lock(
            db,
            deployment_id=job.deployment_id,
            worker_id=worker_id,
            now=ts,
        )
        db.commit()
        return True

    try:
        record_action(
            db,
            deployment_id=dep.id,
            job_id=job.id,
            kind="JOB_EXECUTED",
            payload={
                "job_kind": job.kind,
                "job_scheduled_for": (
                    job.scheduled_for.isoformat() if job.scheduled_for else None
                ),
                "payload": _json_load(job.payload_json),
            },
        )

        if dep.state is not None:
            dep.state.last_evaluated_at = job.scheduled_for or ts
            dep.state.next_evaluate_at = _compute_next_eval(dep, job)
            dep.state.last_error = None
            dep.state.updated_at = ts
            db.add(dep.state)

        mark_job_done(db, job=job, now=ts)
        release_deployment_lock(db, deployment_id=dep.id, worker_id=worker_id, now=ts)
        db.commit()
        return True
    except Exception as exc:
        db.rollback()
        with SessionLocal() as db2:
            try:
                job2 = db2.get(StrategyDeploymentJob, job.id)
                if job2 is not None:
                    mark_job_error(db2, job=job2, error=str(exc), now=ts)
                release_deployment_lock(
                    db2,
                    deployment_id=job.deployment_id,
                    worker_id=worker_id,
                    now=ts,
                )
                db2.commit()
            except Exception:
                db2.rollback()
        logger.exception("Deployment job failed")
        return True


def _worker_loop(worker_id: str) -> None:  # pragma: no cover - background thread
    while not _worker_stop_event.is_set():
        with SessionLocal() as db:
            did_work = execute_job_once(db, worker_id=worker_id)
        if did_work:
            continue
        _worker_stop_event.wait(timeout=0.5)


def schedule_deployment_worker(*, worker_id: str = "worker-1") -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        _worker_started = True

    thread = Thread(
        target=_worker_loop,
        args=(worker_id,),
        name=f"deployment-worker-{worker_id}",
        daemon=True,
    )
    thread.start()


__all__ = ["execute_job_once", "schedule_deployment_worker"]
