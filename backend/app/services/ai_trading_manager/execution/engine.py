from __future__ import annotations

import hashlib
import json
import asyncio
import inspect
import time
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.schemas.ai_trading_manager import DecisionToolCall, TradePlan

from .idempotency_store import IdempotencyStore
from .translator import translate_plan_to_order_intents
from ..broker_adapter import BrokerAdapter, BrokerOrderAck, OrderIntent


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

    def plan_to_order_intents(self, *, plan: TradePlan, correlation_id: str) -> list[OrderIntent]:
        return translate_plan_to_order_intents(plan=plan, correlation_id=correlation_id)

    def _poll_orders_until_converged(
        self,
        *,
        broker: BrokerAdapter,
        account_id: str,
        broker_order_ids: list[str],
        timeout_seconds: float = 3.0,
        poll_interval_seconds: float = 0.5,
    ) -> dict[str, Any]:
        """Best-effort poll for final states.

        Not all broker adapters expose rich order state; this keeps a conservative
        implementation for Phase 1 while maintaining idempotency guarantees.
        """
        t0 = time.perf_counter()
        wanted = {str(x) for x in broker_order_ids if str(x).strip()}
        if not wanted:
            return {"status": "skipped", "reason": "no_order_ids"}

        last_seen: dict[str, dict[str, Any]] = {}
        empty_polls = 0
        while (time.perf_counter() - t0) < float(timeout_seconds):
            try:
                rows = broker.get_orders(account_id=account_id) or []
            except Exception as exc:
                return {"status": "error", "error": str(exc) or "get_orders_failed", "orders": list(last_seen.values())}

            if not rows and not last_seen:
                empty_polls += 1
                if empty_polls >= 2:
                    return {"status": "unavailable", "orders": []}

            for o in rows:
                oid = str(getattr(o, "broker_order_id", None) or getattr(o, "broker_orderid", None) or "")
                if oid in wanted:
                    last_seen[oid] = {
                        "broker_order_id": oid,
                        "status": str(getattr(o, "status", "") or "").upper() or "UNKNOWN",
                        "symbol": getattr(o, "symbol", None),
                        "side": getattr(o, "side", None),
                        "product": getattr(o, "product", None),
                        "qty": getattr(o, "qty", None),
                    }

            if len(last_seen) >= len(wanted):
                terminal = {"COMPLETE", "COMPLETED", "REJECTED", "CANCELLED", "CANCELED"}
                if all(str(v.get("status") or "").upper() in terminal for v in last_seen.values()):
                    return {"status": "converged", "orders": list(last_seen.values())}

            time.sleep(float(poll_interval_seconds))

        return {"status": "timeout", "orders": list(last_seen.values())}

    async def _poll_orders_until_converged_async(
        self,
        *,
        broker: Any,
        account_id: str,
        broker_order_ids: list[str],
        timeout_seconds: float = 4.0,
        poll_interval_seconds: float = 0.6,
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        wanted = {str(x) for x in broker_order_ids if str(x).strip()}
        if not wanted:
            return {"status": "skipped", "reason": "no_order_ids"}

        last_seen: dict[str, dict[str, Any]] = {}
        empty_polls = 0
        while (time.perf_counter() - t0) < float(timeout_seconds):
            try:
                maybe = broker.get_orders(account_id=account_id)
                rows = await maybe if inspect.isawaitable(maybe) else (maybe or [])
            except Exception as exc:
                return {"status": "error", "error": str(exc) or "get_orders_failed", "orders": list(last_seen.values())}

            if not rows and not last_seen:
                empty_polls += 1
                if empty_polls >= 2:
                    return {"status": "unavailable", "orders": []}

            for o in rows:
                oid = str(getattr(o, "broker_order_id", "") or "")
                if oid in wanted:
                    last_seen[oid] = {
                        "broker_order_id": oid,
                        "status": str(getattr(o, "status", "") or "").upper() or "UNKNOWN",
                        "symbol": getattr(o, "symbol", None),
                        "side": getattr(o, "side", None),
                        "product": getattr(o, "product", None),
                        "qty": getattr(o, "qty", None),
                    }

            if len(last_seen) >= len(wanted):
                terminal = {"COMPLETE", "COMPLETED", "REJECTED", "CANCELLED", "CANCELED"}
                if all(str(v.get("status") or "").upper() in terminal for v in last_seen.values()):
                    return {"status": "converged", "orders": list(last_seen.values())}

            await asyncio.sleep(float(poll_interval_seconds))

        return {"status": "timeout", "orders": list(last_seen.values())}

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

    def execute_to_broker(
        self,
        db: Session,
        *,
        user_id: Optional[int],
        account_id: str,
        correlation_id: str,
        plan: TradePlan,
        idempotency_key: str,
        broker: BrokerAdapter,
    ) -> Dict[str, Any]:
        payload = plan.model_dump(mode="json")
        payload_hash = _payload_hash(payload)
        begin = self._idempotency.begin(
            db,
            user_id=user_id,
            account_id=account_id,
            key=idempotency_key,
            payload_hash=payload_hash,
        )
        # If we didn't create it, return prior outcome (idempotency guarantee).
        if not begin.created:
            prev = self._idempotency.read_result(begin.record)
            if prev:
                return prev
            # Fall through if record exists but has empty payload (rare).

        # Safety: do not execute if payload hash mismatches an existing record.
        if not begin.created and str(begin.record.payload_hash or "") != str(payload_hash):
            self._idempotency.mark_status(
                db,
                record_id=begin.record.id,
                status=self._idempotency.STATUS_FAILED,
                result_patch={"error": "IDEMPOTENCY_PAYLOAD_MISMATCH"},
            )
            return {"mode": "execute", "executed": False, "error": "IDEMPOTENCY_PAYLOAD_MISMATCH"}

        intents = self.plan_to_order_intents(plan=plan, correlation_id=correlation_id)
        self._idempotency.mark_status(
            db,
            record_id=begin.record.id,
            status=self._idempotency.STATUS_SUBMITTED,
            result_patch={
                "mode": "execute",
                "plan_id": plan.plan_id,
                "idempotency_record_id": begin.record.id,
                "order_intents": [i.__dict__ for i in intents],
            },
        )

        acks: list[dict[str, Any]] = []
        for intent in intents:
            intent2 = replace(intent, idempotency_key=idempotency_key)
            ack: BrokerOrderAck = broker.place_order(account_id=account_id, intent=intent2)
            acks.append({"symbol": intent.symbol, "broker_order_id": ack.broker_order_id, "status": ack.status})

        poll = self._poll_orders_until_converged(
            broker=broker,
            account_id=account_id,
            broker_order_ids=[a.get("broker_order_id", "") for a in acks],
        )
        result = {
            "mode": "execute",
            "plan_id": plan.plan_id,
            "idempotency_record_id": begin.record.id,
            "orders": acks,
            "poll": poll,
        }
        self._idempotency.mark_status(
            db,
            record_id=begin.record.id,
            status=self._idempotency.STATUS_CONFIRMED,
            result_patch=result,
        )
        return result

    async def execute_to_broker_async(
        self,
        db: Session,
        *,
        user_id: Optional[int],
        account_id: str,
        correlation_id: str,
        plan: TradePlan,
        idempotency_key: str,
        broker: Any,
    ) -> Dict[str, Any]:
        payload = plan.model_dump(mode="json")
        payload_hash = _payload_hash(payload)
        begin = self._idempotency.begin(
            db,
            user_id=user_id,
            account_id=account_id,
            key=idempotency_key,
            payload_hash=payload_hash,
        )
        if not begin.created:
            prev = self._idempotency.read_result(begin.record)
            if prev:
                return prev

        if not begin.created and str(begin.record.payload_hash or "") != str(payload_hash):
            self._idempotency.mark_status(
                db,
                record_id=begin.record.id,
                status=self._idempotency.STATUS_FAILED,
                result_patch={"error": "IDEMPOTENCY_PAYLOAD_MISMATCH"},
            )
            return {"mode": "execute", "executed": False, "error": "IDEMPOTENCY_PAYLOAD_MISMATCH"}

        intents = self.plan_to_order_intents(plan=plan, correlation_id=correlation_id)
        self._idempotency.mark_status(
            db,
            record_id=begin.record.id,
            status=self._idempotency.STATUS_SUBMITTED,
            result_patch={
                "mode": "execute",
                "plan_id": plan.plan_id,
                "idempotency_record_id": begin.record.id,
                "order_intents": [i.__dict__ for i in intents],
            },
        )

        acks: list[dict[str, Any]] = []
        for intent in intents:
            intent2 = replace(intent, idempotency_key=idempotency_key)
            maybe = broker.place_order(account_id=account_id, intent=intent2)
            ack: BrokerOrderAck = await maybe if inspect.isawaitable(maybe) else maybe
            acks.append({"symbol": intent.symbol, "broker_order_id": ack.broker_order_id, "status": ack.status})

        poll = await self._poll_orders_until_converged_async(
            broker=broker,
            account_id=account_id,
            broker_order_ids=[a.get("broker_order_id", "") for a in acks],
        )
        result = {
            "mode": "execute",
            "plan_id": plan.plan_id,
            "idempotency_record_id": begin.record.id,
            "orders": acks,
            "poll": poll,
        }
        self._idempotency.mark_status(
            db,
            record_id=begin.record.id,
            status=self._idempotency.STATUS_CONFIRMED,
            result_patch=result,
        )
        return result
