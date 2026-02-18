from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.schemas.ai_trading_manager import MonitorJob

from .. import audit_store


def upsert_job(db: Session, *, job: MonitorJob, user_id: Optional[int]) -> None:
    audit_store.upsert_monitor_job(db, job, user_id=user_id)


def list_jobs(db: Session, *, account_id: str) -> List[MonitorJob]:
    return audit_store.list_monitor_jobs(db, account_id=account_id)


def delete_job(db: Session, *, monitor_job_id: str) -> bool:
    return audit_store.delete_monitor_job(db, monitor_job_id=monitor_job_id)

