from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import SystemEvent


def record_system_event(
    db: Session,
    *,
    level: str,
    category: str,
    message: str,
    correlation_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> SystemEvent:
    """Persist a system event capturing important backend activity."""

    event = SystemEvent(
        level=level.upper(),
        category=category,
        message=message,
        correlation_id=correlation_id,
        details=json.dumps(details, ensure_ascii=False) if details else None,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


__all__ = ["record_system_event"]
