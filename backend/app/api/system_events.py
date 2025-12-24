from __future__ import annotations

from datetime import UTC, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import SystemEvent
from app.schemas.system_events import (
    SystemEventRead,
    SystemEventsCleanupRequest,
    SystemEventsCleanupResponse,
)

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


@router.get("/", response_model=List[SystemEventRead])
def list_system_events(
    level: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> List[SystemEvent]:
    """Return recent system events, most recent first."""

    query = db.query(SystemEvent)
    if level is not None:
        query = query.filter(SystemEvent.level == level.upper())
    if category is not None:
        query = query.filter(SystemEvent.category == category)

    return (
        query.order_by(SystemEvent.created_at.desc())  # type: ignore[arg-type]
        .limit(limit)
        .all()
    )


@router.post("/cleanup", response_model=SystemEventsCleanupResponse)
def cleanup_system_events(
    payload: SystemEventsCleanupRequest,
    db: Session = Depends(get_db),
) -> SystemEventsCleanupResponse:
    """Delete system events older than max_days."""

    if payload.max_days <= 0:
        remaining = db.query(SystemEvent).count()
        return SystemEventsCleanupResponse(deleted=0, remaining=remaining)

    cutoff = datetime.now(UTC) - payload.max_days_delta()
    q = db.query(SystemEvent).filter(SystemEvent.created_at < cutoff)
    if payload.dry_run:
        deleted = q.count()
    else:
        deleted = q.delete(synchronize_session=False)
        db.commit()
    remaining = db.query(SystemEvent).count()
    return SystemEventsCleanupResponse(deleted=int(deleted), remaining=int(remaining))


__all__ = ["router"]
