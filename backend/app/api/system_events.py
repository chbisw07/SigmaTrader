from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import SystemEvent
from app.schemas.system_events import SystemEventRead

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


__all__ = ["router"]
