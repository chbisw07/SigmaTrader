from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.schemas.ai_trading_manager import DecisionToolCall, TradePlan

from .idempotency_store import IdempotencyStore
from .translator import translate_plan_to_order_intents


def _payload_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class DryRunExecutionResult:
    idempotency_record_id: int
    order_intents: List[Dict[str, Any]]
    tool_calls: List[DecisionToolCall]


class ExecutionEngine:
    def __init__(self, *, idempotency: Optional[IdempotencyStore] = None) -> None:
        self._idempotency = idempotency or IdempotencyStore()

    def dry_run_execute(
        self,
        db: Session,
        *,
        user_id: Optional[int],
        account_id: str,
        correlation_id: str,
        plan: TradePlan,
        idempotency_key: str,
    ) -> DryRunExecutionResult:
        payload = plan.model_dump(mode="json")
        payload_hash = _payload_hash(payload)
        begin = self._idempotency.begin(
            db,
            user_id=user_id,
            account_id=account_id,
            key=idempotency_key,
            payload_hash=payload_hash,
        )

        intents = translate_plan_to_order_intents(plan=plan, correlation_id=correlation_id)
        tool_calls = [
            DecisionToolCall(
                tool_name="execution.dry_run.translate_plan",
                input_summary={"plan_id": plan.plan_id},
                output_summary={"order_intents": len(intents)},
            )
        ]

        # Persist result on the idempotency record for debugging/replay.
        self._idempotency.mark_completed(
            db,
            record_id=begin.record.id,
            result={
                "mode": "dry_run",
                "plan_id": plan.plan_id,
                "order_intents": [i.__dict__ for i in intents],
            },
        )

        return DryRunExecutionResult(
            idempotency_record_id=begin.record.id,
            order_intents=[i.__dict__ for i in intents],
            tool_calls=tool_calls,
        )

