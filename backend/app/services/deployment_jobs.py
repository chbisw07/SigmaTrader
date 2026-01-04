from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    StrategyDeploymentAction,
    StrategyDeploymentJob,
    StrategyDeploymentLock,
)


def _json_dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class JobClaim:
    job: StrategyDeploymentJob
    claimed_at: datetime


def enqueue_job(
    db: Session,
    *,
    deployment_id: int,
    owner_id: int,
    kind: str,
    dedupe_key: str,
    scheduled_for: datetime | None,
    payload: dict[str, Any],
    run_after: datetime | None = None,
    max_attempts: int = 5,
) -> StrategyDeploymentJob | None:
    """Enqueue a job (idempotent by dedupe_key).

    Returns the created job, or None if a duplicate already exists.
    """

    job = StrategyDeploymentJob(
        deployment_id=deployment_id,
        owner_id=owner_id,
        kind=kind,
        status="PENDING",
        dedupe_key=dedupe_key,
        scheduled_for=scheduled_for,
        payload_json=_json_dump(payload),
        run_after=run_after,
        attempts=0,
        max_attempts=max_attempts,
        locked_by=None,
        locked_at=None,
        last_error=None,
    )
    try:
        with db.begin_nested():
            db.add(job)
            db.flush()
    except IntegrityError:
        return None
    return job


def claim_next_job(
    db: Session,
    *,
    worker_id: str,
    now: datetime | None = None,
) -> JobClaim | None:
    """Claim the next runnable PENDING job (SQLite-friendly semantics)."""

    ts = now or datetime.now(UTC)
    job: StrategyDeploymentJob | None = (
        db.query(StrategyDeploymentJob)
        .filter(StrategyDeploymentJob.status == "PENDING")
        .filter(
            (StrategyDeploymentJob.run_after.is_(None))
            | (StrategyDeploymentJob.run_after <= ts)
        )
        .order_by(StrategyDeploymentJob.created_at, StrategyDeploymentJob.id)
        .limit(1)
        .one_or_none()
    )
    if job is None:
        return None

    updated = (
        db.query(StrategyDeploymentJob)
        .filter(StrategyDeploymentJob.id == job.id)
        .filter(StrategyDeploymentJob.status == "PENDING")
        .update(
            {
                "status": "RUNNING",
                "locked_by": worker_id,
                "locked_at": ts,
                "updated_at": ts,
            },
            synchronize_session=False,
        )
    )
    if updated != 1:
        db.rollback()
        return None

    db.flush()
    db.refresh(job)
    return JobClaim(job=job, claimed_at=ts)


def mark_job_done(
    db: Session,
    *,
    job: StrategyDeploymentJob,
    now: datetime | None = None,
) -> None:
    ts = now or datetime.now(UTC)
    job.status = "DONE"
    job.locked_by = None
    job.locked_at = None
    job.run_after = None
    job.last_error = None
    job.updated_at = ts
    db.add(job)


def mark_job_error(
    db: Session,
    *,
    job: StrategyDeploymentJob,
    error: str,
    now: datetime | None = None,
    base_backoff_seconds: float = 2.0,
    max_backoff_seconds: float = 60.0,
) -> None:
    ts = now or datetime.now(UTC)
    job.attempts = int(job.attempts or 0) + 1
    job.last_error = (error or "")[:4000]
    job.locked_by = None
    job.locked_at = None

    if job.attempts >= int(job.max_attempts or 5):
        job.status = "FAILED"
        job.run_after = None
    else:
        job.status = "PENDING"
        delay = base_backoff_seconds * math.pow(2.0, max(0, job.attempts - 1))
        delay = min(delay, max_backoff_seconds)
        job.run_after = ts + timedelta(seconds=float(delay))

    job.updated_at = ts
    db.add(job)


def requeue_stale_running_jobs(
    db: Session,
    *,
    now: datetime | None = None,
    running_ttl_seconds: int = 60,
) -> int:
    """Move stale RUNNING jobs back to PENDING (best-effort)."""

    ts = now or datetime.now(UTC)
    cutoff = ts - timedelta(seconds=running_ttl_seconds)
    updated = (
        db.query(StrategyDeploymentJob)
        .filter(StrategyDeploymentJob.status == "RUNNING")
        .filter(StrategyDeploymentJob.locked_at.isnot(None))
        .filter(StrategyDeploymentJob.locked_at < cutoff)
        .update(
            {
                "status": "PENDING",
                "locked_by": None,
                "locked_at": None,
                "run_after": ts,
                "updated_at": ts,
            },
            synchronize_session=False,
        )
    )
    return int(updated or 0)


def acquire_deployment_lock(
    db: Session,
    *,
    deployment_id: int,
    worker_id: str,
    now: datetime | None = None,
    ttl_seconds: int = 30,
) -> bool:
    """Acquire a per-deployment lock with TTL (SQLite friendly)."""

    ts = now or datetime.now(UTC)
    try:
        with db.begin_nested():
            db.add(
                StrategyDeploymentLock(
                    deployment_id=deployment_id,
                    locked_by=None,
                    locked_until=None,
                )
            )
            db.flush()
    except IntegrityError:
        pass

    updated = (
        db.query(StrategyDeploymentLock)
        .filter(StrategyDeploymentLock.deployment_id == deployment_id)
        .filter(
            (StrategyDeploymentLock.locked_until.is_(None))
            | (StrategyDeploymentLock.locked_until < ts)
        )
        .update(
            {
                "locked_by": worker_id,
                "locked_until": ts + timedelta(seconds=ttl_seconds),
                "updated_at": ts,
            },
            synchronize_session=False,
        )
    )
    return updated == 1


def release_deployment_lock(
    db: Session,
    *,
    deployment_id: int,
    worker_id: str,
    now: datetime | None = None,
) -> None:
    ts = now or datetime.now(UTC)
    (
        db.query(StrategyDeploymentLock)
        .filter(StrategyDeploymentLock.deployment_id == deployment_id)
        .filter(StrategyDeploymentLock.locked_by == worker_id)
        .update(
            {
                "locked_by": None,
                "locked_until": ts,
                "updated_at": ts,
            },
            synchronize_session=False,
        )
    )


def sweep_stale_locks(db: Session, *, now: datetime | None = None) -> int:
    ts = now or datetime.now(UTC)
    updated = (
        db.query(StrategyDeploymentLock)
        .filter(StrategyDeploymentLock.locked_until.isnot(None))
        .filter(StrategyDeploymentLock.locked_until < ts)
        .update(
            {
                "locked_by": None,
                "updated_at": ts,
            },
            synchronize_session=False,
        )
    )
    return int(updated or 0)


def record_action(
    db: Session,
    *,
    deployment_id: int,
    job_id: int | None,
    kind: str,
    payload: dict[str, Any] | None = None,
) -> StrategyDeploymentAction:
    action = StrategyDeploymentAction(
        deployment_id=deployment_id,
        job_id=job_id,
        kind=kind,
        payload_json=_json_dump(payload or {}),
    )
    db.add(action)
    db.flush()
    return action


__all__ = [
    "JobClaim",
    "acquire_deployment_lock",
    "claim_next_job",
    "enqueue_job",
    "mark_job_done",
    "mark_job_error",
    "record_action",
    "release_deployment_lock",
    "requeue_stale_running_jobs",
    "sweep_stale_locks",
]
