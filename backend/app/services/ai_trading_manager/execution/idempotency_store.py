from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.ai_trading_manager import AiTmIdempotencyRecord


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def _json_loads(raw: str, fallback: Any) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return fallback


@dataclass(frozen=True)
class IdempotencyBeginResult:
    record: AiTmIdempotencyRecord
    created: bool


class IdempotencyStore:
    def begin(
        self,
        db: Session,
        *,
        user_id: Optional[int],
        account_id: str,
        key: str,
        payload_hash: str,
    ) -> IdempotencyBeginResult:
        # Optimistic create; fall back to fetch on unique constraint collision.
        now = datetime.now(UTC)
        row = AiTmIdempotencyRecord(
            user_id=user_id,
            account_id=account_id,
            idempotency_key=key,
            payload_hash=payload_hash,
            status="STARTED",
            result_json="{}",
            first_seen_at=now,
            updated_at=now,
        )
        db.add(row)
        try:
            db.commit()
            db.refresh(row)
            return IdempotencyBeginResult(record=row, created=True)
        except IntegrityError:
            db.rollback()
            existing = db.execute(
                select(AiTmIdempotencyRecord).where(
                    AiTmIdempotencyRecord.account_id == account_id,
                    AiTmIdempotencyRecord.idempotency_key == key,
                )
            ).scalar_one()
            return IdempotencyBeginResult(record=existing, created=False)

    def mark_completed(
        self,
        db: Session,
        *,
        record_id: int,
        result: Dict[str, Any],
    ) -> AiTmIdempotencyRecord:
        row = db.get(AiTmIdempotencyRecord, record_id)
        if row is None:
            raise ValueError("Idempotency record not found.")
        row.status = "COMPLETED"
        row.result_json = _json_dumps(result)
        row.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(row)
        return row

    def read_result(self, row: AiTmIdempotencyRecord) -> Dict[str, Any]:
        return _json_loads(row.result_json, {})
