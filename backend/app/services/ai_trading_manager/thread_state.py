from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models import AiTmThreadState


THREAD_STATE_SCHEMA_VERSION = "v1"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def _json_loads(raw: str, fallback: Any) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def default_thread_state() -> Dict[str, Any]:
    return {
        "schema_version": THREAD_STATE_SCHEMA_VERSION,
        # Tavily guardrails.
        "tavily_calls_session": 0,
        "tavily_extra_calls_allowed": 0,
        # Remote detailed portfolio approvals.
        "portfolio_access_approved": False,  # "Allow once" (consumed after one detailed tool call)
        "portfolio_access_session": False,  # "Allow for this session/thread"
    }


def get_or_create_thread_state(
    db: Session,
    *,
    account_id: str,
    thread_id: str,
    user_id: Optional[int],
) -> Dict[str, Any]:
    row = (
        db.query(AiTmThreadState)
        .filter(AiTmThreadState.account_id == account_id, AiTmThreadState.thread_id == thread_id)
        .one_or_none()
    )
    if row is None:
        now = datetime.now(UTC)
        row = AiTmThreadState(
            account_id=account_id,
            thread_id=thread_id,
            user_id=user_id,
            state_json=_json_dumps(default_thread_state()),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    st = _json_loads(getattr(row, "state_json", "") or "{}", {})
    if not isinstance(st, dict):
        st = {}
    merged = {**default_thread_state(), **st}
    if merged != st:
        row.state_json = _json_dumps(merged)
        row.updated_at = datetime.now(UTC)
        db.add(row)
        db.commit()
    return merged


def patch_thread_state(
    db: Session,
    *,
    account_id: str,
    thread_id: str,
    user_id: Optional[int],
    patch: Dict[str, Any],
) -> Dict[str, Any]:
    base = get_or_create_thread_state(db, account_id=account_id, thread_id=thread_id, user_id=user_id)
    next_state = dict(base)
    for k, v in (patch or {}).items():
        next_state[str(k)] = v
    row = (
        db.query(AiTmThreadState)
        .filter(AiTmThreadState.account_id == account_id, AiTmThreadState.thread_id == thread_id)
        .one_or_none()
    )
    if row is None:
        # Should not happen because get_or_create_thread_state created it; be defensive.
        now = datetime.now(UTC)
        row = AiTmThreadState(
            account_id=account_id,
            thread_id=thread_id,
            user_id=user_id,
            state_json=_json_dumps(next_state),
            created_at=now,
            updated_at=now,
        )
    row.user_id = user_id
    row.state_json = _json_dumps(next_state)
    row.updated_at = datetime.now(UTC)
    db.add(row)
    db.commit()
    return next_state

