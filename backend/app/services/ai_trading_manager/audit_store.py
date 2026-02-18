from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.ai_trading_manager import (
    AiTmBrokerSnapshot,
    AiTmChatMessage,
    AiTmDecisionTrace,
    AiTmException,
    AiTmLedgerSnapshot,
    AiTmMonitorJob,
    AiTmReconciliationRun,
)
from app.schemas.ai_trading_manager import (
    AiTmMessage,
    AiTmMessageRole,
    AiTmThread,
    BrokerSnapshot,
    DecisionTrace,
    LedgerSnapshot,
    MonitorJob,
    ReconciliationDelta,
)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def _json_loads(raw: str, fallback: Any) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return fallback


@dataclass(frozen=True)
class StoredSnapshotRefs:
    broker_snapshot_id: Optional[int]
    ledger_snapshot_id: Optional[int]


def persist_broker_snapshot(
    db: Session,
    snapshot: BrokerSnapshot,
    *,
    user_id: Optional[int],
) -> AiTmBrokerSnapshot:
    row = AiTmBrokerSnapshot(
        user_id=user_id,
        account_id=snapshot.account_id,
        as_of_ts=snapshot.as_of_ts,
        source=snapshot.source,
        payload_json=_json_dumps(snapshot.model_dump(mode="json")),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def persist_ledger_snapshot(
    db: Session,
    snapshot: LedgerSnapshot,
    *,
    user_id: Optional[int],
) -> AiTmLedgerSnapshot:
    row = AiTmLedgerSnapshot(
        user_id=user_id,
        account_id=snapshot.account_id,
        as_of_ts=snapshot.as_of_ts,
        payload_json=_json_dumps(snapshot.model_dump(mode="json")),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def persist_decision_trace(
    db: Session,
    trace: DecisionTrace,
    *,
    user_id: Optional[int],
) -> AiTmDecisionTrace:
    row = AiTmDecisionTrace(
        decision_id=trace.decision_id,
        correlation_id=trace.correlation_id,
        user_id=user_id,
        account_id=trace.account_id,
        user_message=trace.user_message,
        inputs_json=_json_dumps(trace.inputs_used),
        tools_json=_json_dumps([t.model_dump(mode="json") for t in trace.tools_called]),
        riskgate_json=_json_dumps(trace.riskgate_result.model_dump(mode="json")) if trace.riskgate_result else None,
        outcome_json=_json_dumps(trace.final_outcome),
        explanations_json=_json_dumps(trace.explanations),
        created_at=trace.created_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def new_decision_trace(
    *,
    correlation_id: str,
    account_id: str,
    user_message: str,
    inputs_used: Optional[Dict[str, Any]] = None,
) -> DecisionTrace:
    return DecisionTrace(
        decision_id=uuid4().hex,
        correlation_id=correlation_id,
        created_at=datetime.now(UTC),
        account_id=account_id,
        user_message=user_message,
        inputs_used=inputs_used or {},
        tools_called=[],
        riskgate_result=None,
        final_outcome={},
        explanations=[],
    )


def list_decision_traces(
    db: Session,
    *,
    account_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[DecisionTrace]:
    stmt = select(AiTmDecisionTrace).order_by(desc(AiTmDecisionTrace.created_at)).limit(limit).offset(offset)
    if account_id:
        stmt = stmt.where(AiTmDecisionTrace.account_id == account_id)
    rows = db.execute(stmt).scalars().all()
    traces: List[DecisionTrace] = []
    for r in rows:
        traces.append(
            DecisionTrace(
                decision_id=r.decision_id,
                correlation_id=r.correlation_id,
                created_at=r.created_at,
                account_id=r.account_id,
                user_message=r.user_message,
                inputs_used=_json_loads(r.inputs_json, {}),
                tools_called=[],
                riskgate_result=None,
                final_outcome=_json_loads(r.outcome_json, {}),
                explanations=_json_loads(r.explanations_json, []),
            )
        )
    return traces


def get_decision_trace(db: Session, *, decision_id: str) -> Optional[DecisionTrace]:
    row = db.execute(select(AiTmDecisionTrace).where(AiTmDecisionTrace.decision_id == decision_id)).scalar_one_or_none()
    if row is None:
        return None
    return DecisionTrace(
        decision_id=row.decision_id,
        correlation_id=row.correlation_id,
        created_at=row.created_at,
        account_id=row.account_id,
        user_message=row.user_message,
        inputs_used=_json_loads(row.inputs_json, {}),
        tools_called=[],
        riskgate_result=None,
        final_outcome=_json_loads(row.outcome_json, {}),
        explanations=_json_loads(row.explanations_json, []),
    )


def append_chat_messages(
    db: Session,
    *,
    user_id: Optional[int],
    account_id: str,
    thread_id: str,
    messages: Iterable[AiTmMessage],
) -> None:
    for m in messages:
        db.add(
            AiTmChatMessage(
                message_id=m.message_id,
                thread_id=thread_id,
                account_id=account_id,
                user_id=user_id,
                role=m.role.value if isinstance(m.role, AiTmMessageRole) else str(m.role),
                content=m.content,
                correlation_id=m.correlation_id,
                decision_id=m.decision_id,
                created_at=m.created_at,
            )
        )
    db.commit()


def get_thread(db: Session, *, account_id: str, thread_id: str = "default", limit: int = 200) -> AiTmThread:
    stmt = (
        select(AiTmChatMessage)
        .where(AiTmChatMessage.account_id == account_id, AiTmChatMessage.thread_id == thread_id)
        .order_by(AiTmChatMessage.created_at)
        .limit(limit)
    )
    rows = db.execute(stmt).scalars().all()
    msgs: List[AiTmMessage] = []
    for r in rows:
        try:
            role = AiTmMessageRole(r.role)
        except Exception:
            role = AiTmMessageRole.system
        msgs.append(
            AiTmMessage(
                message_id=r.message_id,
                role=role,
                content=r.content,
                created_at=r.created_at,
                correlation_id=r.correlation_id,
                decision_id=r.decision_id,
            )
        )
    return AiTmThread(thread_id=thread_id, account_id=account_id, messages=msgs)


def persist_reconciliation_run(
    db: Session,
    *,
    user_id: Optional[int],
    account_id: str,
    broker_snapshot_id: Optional[int],
    ledger_snapshot_id: Optional[int],
    deltas: List[ReconciliationDelta],
) -> AiTmReconciliationRun:
    row = AiTmReconciliationRun(
        run_id=uuid4().hex,
        user_id=user_id,
        account_id=account_id,
        broker_snapshot_id=broker_snapshot_id,
        ledger_snapshot_id=ledger_snapshot_id,
        deltas_json=_json_dumps([d.model_dump(mode="json") for d in deltas]),
        created_at=datetime.now(UTC),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def open_exceptions_for_deltas(
    db: Session,
    *,
    user_id: Optional[int],
    account_id: str,
    run_id: str,
    deltas: Iterable[ReconciliationDelta],
) -> List[AiTmException]:
    created: List[AiTmException] = []
    for d in deltas:
        if d.severity.value not in {"M", "H"}:
            continue
        row = AiTmException(
            exception_id=uuid4().hex,
            user_id=user_id,
            account_id=account_id,
            exception_type=d.delta_type,
            severity=d.severity.value,
            key=d.key,
            summary=d.summary,
            details_json=_json_dumps(
                {
                    "broker_ref": d.broker_ref,
                    "expected_ref": d.expected_ref,
                }
            ),
            status="OPEN",
            related_run_id=run_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(row)
        created.append(row)
    try:
        db.commit()
    except Exception:
        # Dedupe via unique constraint; keep best-effort behavior.
        db.rollback()
    return created


def list_exceptions(
    db: Session,
    *,
    account_id: Optional[str] = None,
    status: str = "OPEN",
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    stmt = select(AiTmException).order_by(desc(AiTmException.created_at)).where(AiTmException.status == status)
    if account_id:
        stmt = stmt.where(AiTmException.account_id == account_id)
    stmt = stmt.limit(limit).offset(offset)
    rows = db.execute(stmt).scalars().all()
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "exception_id": r.exception_id,
                "account_id": r.account_id,
                "exception_type": r.exception_type,
                "severity": r.severity,
                "key": r.key,
                "summary": r.summary,
                "status": r.status,
                "details": _json_loads(r.details_json, {}),
                "related_decision_id": r.related_decision_id,
                "related_run_id": r.related_run_id,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
        )
    return out


def get_exception(db: Session, *, exception_id: str) -> Optional[Dict[str, Any]]:
    row = db.execute(select(AiTmException).where(AiTmException.exception_id == exception_id)).scalar_one_or_none()
    if row is None:
        return None
    return {
        "exception_id": row.exception_id,
        "account_id": row.account_id,
        "exception_type": row.exception_type,
        "severity": row.severity,
        "key": row.key,
        "summary": row.summary,
        "status": row.status,
        "details": _json_loads(row.details_json, {}),
        "related_decision_id": row.related_decision_id,
        "related_run_id": row.related_run_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def upsert_monitor_job(
    db: Session,
    job: MonitorJob,
    *,
    user_id: Optional[int],
) -> AiTmMonitorJob:
    existing = db.execute(
        select(AiTmMonitorJob).where(AiTmMonitorJob.monitor_job_id == job.monitor_job_id)
    ).scalar_one_or_none()
    payload = _json_dumps(job.model_dump(mode="json"))
    now = datetime.now(UTC)
    if existing is None:
        row = AiTmMonitorJob(
            monitor_job_id=job.monitor_job_id,
            user_id=user_id,
            account_id=job.account_id,
            enabled=job.enabled,
            cadence_sec=job.cadence_sec,
            job_json=payload,
            next_run_at=None,
            last_run_at=None,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    existing.enabled = job.enabled
    existing.cadence_sec = job.cadence_sec
    existing.job_json = payload
    existing.updated_at = now
    db.commit()
    db.refresh(existing)
    return existing


def list_monitor_jobs(db: Session, *, account_id: str) -> List[MonitorJob]:
    rows = db.execute(
        select(AiTmMonitorJob).where(AiTmMonitorJob.account_id == account_id).order_by(desc(AiTmMonitorJob.created_at))
    ).scalars().all()
    out: List[MonitorJob] = []
    for r in rows:
        raw = _json_loads(r.job_json, {})
        try:
            out.append(MonitorJob.model_validate(raw))
        except Exception:
            # Fall back to a minimal representation if row is corrupt.
            out.append(
                MonitorJob(
                    monitor_job_id=r.monitor_job_id,
                    account_id=r.account_id,
                    enabled=r.enabled,
                    symbols=[],
                    conditions=[],
                    cadence_sec=r.cadence_sec,
                    window={},
                )
            )
    return out


def delete_monitor_job(db: Session, *, monitor_job_id: str) -> bool:
    row = db.execute(select(AiTmMonitorJob).where(AiTmMonitorJob.monitor_job_id == monitor_job_id)).scalar_one_or_none()
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
