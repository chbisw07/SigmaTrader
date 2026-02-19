from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.ai_trading_manager import AiTmOperatorPayload


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def _items_count(payload: Any) -> int:
    if payload is None:
        return 0
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        if isinstance(payload.get("net"), list):
            return len(payload.get("net") or [])
        if isinstance(payload.get("holdings"), list):
            return len(payload.get("holdings") or [])
        return len(payload)
    return 1


def persist_operator_payload(
    db: Session,
    *,
    decision_id: str,
    tool_name: str,
    tool_call_id: str,
    account_id: str,
    user_id: Optional[int],
    payload: Any,
) -> dict[str, Any]:
    raw = _json_dumps(payload)
    payload_id = uuid4().hex
    row = AiTmOperatorPayload(
        payload_id=payload_id,
        decision_id=str(decision_id),
        tool_name=str(tool_name),
        tool_call_id=str(tool_call_id),
        account_id=str(account_id or "default"),
        user_id=user_id,
        payload_json=raw,
        payload_bytes=len(raw.encode("utf-8")),
        items_count=_items_count(payload),
        created_at=datetime.now(UTC),
    )
    db.add(row)
    db.commit()
    return {
        "payload_id": payload_id,
        "payload_bytes": int(row.payload_bytes),
        "items_count": int(row.items_count),
    }


__all__ = ["persist_operator_payload"]

