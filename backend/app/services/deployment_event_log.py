from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import StrategyDeploymentEventLog


def _json_dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


def emit_deployment_event(
    db: Session,
    *,
    deployment_id: int,
    kind: str,
    job_id: int | None = None,
    created_at: datetime | None = None,
    payload: dict[str, Any] | None = None,
) -> StrategyDeploymentEventLog:
    event = StrategyDeploymentEventLog(
        deployment_id=int(deployment_id),
        job_id=(int(job_id) if job_id is not None else None),
        kind=str(kind),
        payload_json=_json_dump(payload or {}),
        created_at=created_at or datetime.now(UTC),
    )
    db.add(event)
    db.flush()
    return event


__all__ = ["emit_deployment_event"]
