from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user_optional
from app.core.config import Settings, get_settings
from app.core.logging import log_with_correlation
from app.db.session import get_db
from app.models import User
from app.schemas.ai_trading_manager import (
    AiTmMessage,
    AiTmMessageRole,
    AiTmThread,
    AiTmUserMessageRequest,
    AiTmUserMessageResponse,
    MonitorJob,
)
from app.services.ai_trading_manager import audit_store
from app.services.ai_trading_manager.broker_factory import get_broker_adapter
from app.services.ai_trading_manager.feature_flags import (
    require_ai_assistant_enabled,
    require_monitoring_enabled,
)
from app.services.ai_trading_manager.ledger_snapshot import build_ledger_snapshot
from app.services.ai_trading_manager.monitoring.dsl import validate_monitor_job
from app.services.ai_trading_manager.reconciler import run_reconciler

# ruff: noqa: B008  # FastAPI dependency injection pattern

logger = logging.getLogger(__name__)
router = APIRouter()


def _correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", None) or request.headers.get("X-Request-ID") or uuid4().hex


@router.get("/thread", response_model=AiTmThread)
def get_thread(
    request: Request,
    account_id: str = "default",
    thread_id: str = "default",
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> AiTmThread:
    require_ai_assistant_enabled(settings)
    log_with_correlation(logger, request, logging.INFO, "ai_tm.thread.read", account_id=account_id, thread_id=thread_id)
    return audit_store.get_thread(db, account_id=account_id, thread_id=thread_id)


@router.post("/messages", response_model=AiTmUserMessageResponse)
def post_message(
    payload: AiTmUserMessageRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
) -> AiTmUserMessageResponse:
    require_ai_assistant_enabled(settings)
    corr = _correlation_id(request)
    user_id = user.id if user is not None else None

    user_msg = AiTmMessage(
        message_id=uuid4().hex,
        role=AiTmMessageRole.user,
        content=payload.content,
        created_at=datetime.now(UTC),
        correlation_id=corr,
    )

    trace = audit_store.new_decision_trace(
        correlation_id=corr,
        account_id=payload.account_id,
        user_message=payload.content,
        inputs_used={"mode": "phase0_stub"},
    )

    assistant_text = "Phase 0 stub: I can record messages, show traces, and run reconciliation (stub broker)."
    assistant_msg = AiTmMessage(
        message_id=uuid4().hex,
        role=AiTmMessageRole.assistant,
        content=assistant_text,
        created_at=datetime.now(UTC),
        correlation_id=corr,
        decision_id=trace.decision_id,
    )

    audit_store.append_chat_messages(
        db,
        user_id=user_id,
        account_id=payload.account_id,
        thread_id="default",
        messages=[user_msg, assistant_msg],
    )
    audit_store.persist_decision_trace(db, trace, user_id=user_id)

    log_with_correlation(
        logger,
        request,
        logging.INFO,
        "ai_tm.message.persisted",
        account_id=payload.account_id,
        decision_id=trace.decision_id,
    )
    thread = audit_store.get_thread(db, account_id=payload.account_id, thread_id="default")
    return AiTmUserMessageResponse(thread=thread, decision_id=trace.decision_id)


@router.get("/decision-traces")
def list_traces(
    request: Request,
    account_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    require_ai_assistant_enabled(settings)
    traces = audit_store.list_decision_traces(db, account_id=account_id, limit=min(limit, 200), offset=max(offset, 0))
    log_with_correlation(
        logger,
        request,
        logging.INFO,
        "ai_tm.decision_traces.list",
        account_id=account_id,
        limit=limit,
        offset=offset,
        returned=len(traces),
    )
    return [t.model_dump(mode="json") for t in traces]


@router.get("/decision-traces/{decision_id}")
def get_trace(
    decision_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    require_ai_assistant_enabled(settings)
    trace = audit_store.get_decision_trace(db, decision_id=decision_id)
    if trace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision trace not found.")
    log_with_correlation(logger, request, logging.INFO, "ai_tm.decision_trace.get", decision_id=decision_id)
    return trace.model_dump(mode="json")


@router.post("/reconcile")
def reconcile_now(
    request: Request,
    account_id: str = "default",
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
    require_ai_assistant_enabled(settings)
    corr = _correlation_id(request)
    user_id = user.id if user is not None else None

    adapter = get_broker_adapter(settings)
    broker_snapshot = adapter.get_snapshot(account_id=account_id)
    ledger_snapshot = build_ledger_snapshot(db, account_id=account_id)

    broker_row = audit_store.persist_broker_snapshot(db, broker_snapshot, user_id=user_id)
    ledger_row = audit_store.persist_ledger_snapshot(db, ledger_snapshot, user_id=user_id)

    result = run_reconciler(broker=broker_snapshot, ledger=ledger_snapshot)
    run_row = audit_store.persist_reconciliation_run(
        db,
        user_id=user_id,
        account_id=account_id,
        broker_snapshot_id=broker_row.id,
        ledger_snapshot_id=ledger_row.id,
        deltas=result.deltas,
    )
    audit_store.open_exceptions_for_deltas(
        db,
        user_id=user_id,
        account_id=account_id,
        run_id=run_row.run_id,
        deltas=result.deltas,
    )

    trace = audit_store.new_decision_trace(
        correlation_id=corr,
        account_id=account_id,
        user_message="reconcile_now",
        inputs_used={
            "broker_snapshot_id": broker_row.id,
            "ledger_snapshot_id": ledger_row.id,
            "reconciliation_run_id": run_row.run_id,
            "adapter": adapter.name,
        },
    )
    trace.final_outcome = {
        "type": "RECONCILIATION_RUN",
        "run_id": run_row.run_id,
        "delta_count": len(result.deltas),
        "severity_counts": result.severity_counts,
    }
    audit_store.persist_decision_trace(db, trace, user_id=user_id)

    log_with_correlation(
        logger,
        request,
        logging.INFO,
        "ai_tm.reconcile.run",
        account_id=account_id,
        run_id=run_row.run_id,
        delta_count=len(result.deltas),
    )
    return {
        "run_id": run_row.run_id,
        "deltas": [d.model_dump(mode="json") for d in result.deltas],
        "severity_counts": result.severity_counts,
        "decision_id": trace.decision_id,
    }


@router.get("/exceptions")
def list_exceptions(
    request: Request,
    account_id: str | None = None,
    status_filter: str = "OPEN",
    limit: int = 100,
    offset: int = 0,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    require_ai_assistant_enabled(settings)
    rows = audit_store.list_exceptions(
        db,
        account_id=account_id,
        status=status_filter,
        limit=min(limit, 500),
        offset=max(offset, 0),
    )
    log_with_correlation(
        logger,
        request,
        logging.INFO,
        "ai_tm.exceptions.list",
        account_id=account_id,
        status=status_filter,
        returned=len(rows),
    )
    return rows


@router.get("/exceptions/{exception_id}")
def get_exception(
    exception_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    require_ai_assistant_enabled(settings)
    row = audit_store.get_exception(db, exception_id=exception_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exception not found.")
    log_with_correlation(logger, request, logging.INFO, "ai_tm.exception.get", exception_id=exception_id)
    return row


@router.get("/monitor-jobs")
def list_monitor_jobs(
    request: Request,
    account_id: str = "default",
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    require_ai_assistant_enabled(settings)
    require_monitoring_enabled(settings)
    jobs = audit_store.list_monitor_jobs(db, account_id=account_id)
    log_with_correlation(logger, request, logging.INFO, "ai_tm.monitor_jobs.list", account_id=account_id, n=len(jobs))
    return [j.model_dump(mode="json") for j in jobs]


@router.post("/monitor-jobs", status_code=201)
def upsert_monitor_job(
    payload: MonitorJob,
    request: Request,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
    require_ai_assistant_enabled(settings)
    require_monitoring_enabled(settings)
    errs = validate_monitor_job(payload)
    if errs:
        raise HTTPException(status_code=400, detail=",".join(errs))
    user_id = user.id if user is not None else None
    audit_store.upsert_monitor_job(db, payload, user_id=user_id)

    trace = audit_store.new_decision_trace(
        correlation_id=_correlation_id(request),
        account_id=payload.account_id,
        user_message="monitor_job_upsert",
        inputs_used={"monitor_job_id": payload.monitor_job_id},
    )
    trace.final_outcome = {"type": "MONITOR_JOB_UPSERT", "monitor_job_id": payload.monitor_job_id}
    audit_store.persist_decision_trace(db, trace, user_id=user_id)

    log_with_correlation(
        logger,
        request,
        logging.INFO,
        "ai_tm.monitor_job.upsert",
        monitor_job_id=payload.monitor_job_id,
        account_id=payload.account_id,
    )
    return {"monitor_job_id": payload.monitor_job_id, "decision_id": trace.decision_id}


@router.delete("/monitor-jobs/{monitor_job_id}", status_code=204)
def delete_monitor_job(
    monitor_job_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> None:
    require_ai_assistant_enabled(settings)
    require_monitoring_enabled(settings)
    ok = audit_store.delete_monitor_job(db, monitor_job_id=monitor_job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Monitor job not found.")
    log_with_correlation(logger, request, logging.INFO, "ai_tm.monitor_job.delete", monitor_job_id=monitor_job_id)
    return None

