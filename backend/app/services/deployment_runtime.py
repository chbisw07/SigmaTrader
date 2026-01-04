from __future__ import annotations

from datetime import UTC, datetime

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import StrategyDeployment
from app.services.deployment_reconciler import (
    reconcile_deployment_once,
    schedule_deployment_reconciler,
)
from app.services.deployment_scheduler import (
    enqueue_due_jobs_once,
    schedule_deployment_scheduler,
)
from app.services.deployment_sweeper import schedule_deployment_sweeper, sweep_once
from app.services.deployment_worker import execute_job_once, schedule_deployment_worker


def start_deployments_runtime(*, mode: str = "threads") -> None:
    """Start deployment runtime services.

    mode:
    - threads: start background threads (scheduler/worker/sweeper/reconciler)
    - once: run a single pass of each component (smoke-test friendly)
    """

    m = (mode or "threads").strip().lower()
    if m == "once":
        settings = get_settings()
        with SessionLocal() as db:
            enqueue_due_jobs_once(db, settings, prefetch_candles=False)
            db.commit()
        with SessionLocal() as db:
            execute_job_once(db, worker_id="runtime-once", now=datetime.now(UTC))
        sweep_once()
        # Reconcile enabled deployments best-effort.
        with SessionLocal() as db:
            ids = (
                db.query(StrategyDeployment.id)
                .filter(StrategyDeployment.enabled.is_(True))
                .order_by(StrategyDeployment.id)
                .all()
            )
            for (dep_id,) in ids:
                try:
                    reconcile_deployment_once(db, deployment_id=int(dep_id))
                except Exception:
                    db.rollback()
        return

    schedule_deployment_scheduler()
    schedule_deployment_worker(worker_id="worker-1")
    schedule_deployment_sweeper()
    schedule_deployment_reconciler()


__all__ = ["start_deployments_runtime"]
