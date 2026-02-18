from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
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
    MarketContextResponse,
    MonitorJob,
    PlaybookCreateRequest,
    PortfolioDiagnostics,
    SizingSuggestRequest,
    SizingSuggestResponse,
    TradePlanCreateRequest,
)
from app.services.ai_trading_manager import audit_store
from app.services.ai_trading_manager.broker_factory import get_broker_adapter
from app.services.ai_trading_manager.ai_settings_config import get_ai_settings_with_source
from app.services.ai_trading_manager.execution.engine import ExecutionEngine
from app.services.ai_trading_manager.expected_ledger import resync_expected_positions
from app.services.ai_trading_manager.feature_flags import (
    require_ai_assistant_enabled,
    require_execution_enabled,
    require_monitoring_enabled,
)
from app.services.ai_trading_manager.ledger_snapshot import build_ledger_snapshot
from app.services.ai_trading_manager.monitoring.dsl import validate_monitor_job
from app.services.ai_trading_manager.plan_engine import new_plan_from_intent, normalize_trade_plan
from app.services.ai_trading_manager.playbooks import (
    create_playbook,
    create_playbook_run,
    get_playbook,
    get_trade_plan,
    list_playbook_runs,
    list_playbooks,
    set_playbook_armed,
    touch_playbook_after_run,
    upsert_trade_plan,
)
from app.services.ai_trading_manager.market_context import build_market_context_overlay
from app.services.ai_trading_manager.portfolio_diagnostics import build_portfolio_diagnostics
from app.services.ai_trading_manager.reconciler import run_reconciler
from app.services.ai_trading_manager.riskgate.engine import evaluate_riskgate
from app.services.ai_trading_manager.sizing import extract_equity_value, suggest_qty
from app.models.ai_trading_manager import AiTmChatMessage
from app.services.kite_mcp.snapshot import fetch_kite_mcp_snapshot

# ruff: noqa: B008  # FastAPI dependency injection pattern

logger = logging.getLogger(__name__)
router = APIRouter()


def _correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", None) or request.headers.get("X-Request-ID") or uuid4().hex


def _validate_authorization_message_id(db: Session, *, message_id: str) -> None:
    msg = db.execute(select(AiTmChatMessage).where(AiTmChatMessage.message_id == message_id)).scalar_one_or_none()
    if msg is None or str(msg.role).lower() != "user":
        raise HTTPException(status_code=400, detail="authorization_message_id must reference a user message.")


def _attach_quotes(
    *,
    adapter: Any,
    broker_snapshot: Any,
    account_id: str,
    symbols: List[str],
) -> Any:
    if not symbols:
        return broker_snapshot
    try:
        quotes = adapter.get_quotes(account_id=account_id, symbols=[str(s).upper() for s in symbols])
        return broker_snapshot.model_copy(update={"quotes_cache": quotes})
    except Exception:
        return broker_snapshot


@router.get("/thread", response_model=AiTmThread)
def get_thread(
    request: Request,
    account_id: str = "default",
    thread_id: str = "default",
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> AiTmThread:
    require_ai_assistant_enabled(db, settings)
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
    require_ai_assistant_enabled(db, settings)
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
    require_ai_assistant_enabled(db, settings)
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
    require_ai_assistant_enabled(db, settings)
    trace = audit_store.get_decision_trace(db, decision_id=decision_id)
    if trace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision trace not found.")
    log_with_correlation(logger, request, logging.INFO, "ai_tm.decision_trace.get", decision_id=decision_id)
    return trace.model_dump(mode="json")


@router.post("/reconcile")
async def reconcile_now(
    request: Request,
    account_id: str = "default",
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
    require_ai_assistant_enabled(db, settings)
    corr = _correlation_id(request)
    user_id = user.id if user is not None else None

    cfg, _src = get_ai_settings_with_source(db, settings)
    adapter_name = "stub"
    if cfg.feature_flags.kite_mcp_enabled:
        try:
            broker_snapshot = await fetch_kite_mcp_snapshot(db, settings, account_id=account_id)
            adapter_name = "kite_mcp"
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc) or "Kite MCP snapshot fetch failed.") from exc
    else:
        adapter = get_broker_adapter(db, settings=settings, user_id=user_id)
        adapter_name = adapter.name
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
            "adapter": adapter_name,
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
    require_ai_assistant_enabled(db, settings)
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
    require_ai_assistant_enabled(db, settings)
    row = audit_store.get_exception(db, exception_id=exception_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exception not found.")
    log_with_correlation(logger, request, logging.INFO, "ai_tm.exception.get", exception_id=exception_id)
    return row


@router.post("/exceptions/{exception_id}/ack", response_model=dict)
def ack_exception_api(
    exception_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
    require_ai_assistant_enabled(db, settings)
    user_id = user.id if user is not None else None
    row = audit_store.ack_exception(db, exception_id=exception_id, status="ACK")
    if row is None:
        raise HTTPException(status_code=404, detail="Exception not found.")

    trace = audit_store.new_decision_trace(
        correlation_id=_correlation_id(request),
        account_id=row["account_id"],
        user_message="exception_ack",
        inputs_used={"exception_id": exception_id},
    )
    trace.final_outcome = {"type": "EXCEPTION_ACK", "exception_id": exception_id}
    audit_store.persist_decision_trace(db, trace, user_id=user_id)
    return {"exception": row, "decision_id": trace.decision_id}


@router.get("/monitor-jobs")
def list_monitor_jobs(
    request: Request,
    account_id: str = "default",
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    require_ai_assistant_enabled(db, settings)
    require_monitoring_enabled(db, settings)
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
    require_ai_assistant_enabled(db, settings)
    require_monitoring_enabled(db, settings)
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
    require_ai_assistant_enabled(db, settings)
    require_monitoring_enabled(db, settings)
    ok = audit_store.delete_monitor_job(db, monitor_job_id=monitor_job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Monitor job not found.")
    log_with_correlation(logger, request, logging.INFO, "ai_tm.monitor_job.delete", monitor_job_id=monitor_job_id)
    return None


@router.post("/expected-ledger/resync", response_model=dict)
def resync_expected_ledger(
    request: Request,
    account_id: str = "default",
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
    require_ai_assistant_enabled(db, settings)
    user_id = user.id if user is not None else None
    adapter = get_broker_adapter(db, settings=settings, user_id=user_id)
    broker_snapshot = adapter.get_snapshot(account_id=account_id)
    updated = resync_expected_positions(db, account_id=account_id, broker_snapshot=broker_snapshot)

    trace = audit_store.new_decision_trace(
        correlation_id=_correlation_id(request),
        account_id=account_id,
        user_message="expected_ledger_resync",
        inputs_used={"adapter": adapter.name, "updated_positions": updated},
    )
    trace.final_outcome = {"type": "EXPECTED_LEDGER_RESYNC", "updated_positions": updated}
    audit_store.persist_decision_trace(db, trace, user_id=user_id)

    return {"updated_positions": updated, "decision_id": trace.decision_id}


@router.post("/trade-plans", response_model=dict)
def create_trade_plan(
    payload: TradePlanCreateRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
    require_ai_assistant_enabled(db, settings)
    user_id = user.id if user is not None else None

    plan = new_plan_from_intent(payload.intent)
    plan = normalize_trade_plan(plan)
    upsert_trade_plan(db, plan=plan, user_id=user_id, account_id=payload.account_id)

    trace = audit_store.new_decision_trace(
        correlation_id=_correlation_id(request),
        account_id=payload.account_id,
        user_message="trade_plan_create",
        inputs_used={"plan_id": plan.plan_id},
    )
    trace.final_outcome = {"type": "TRADE_PLAN_CREATED", "plan_id": plan.plan_id}
    audit_store.persist_decision_trace(db, trace, user_id=user_id)

    return {"plan": plan.model_dump(mode="json"), "decision_id": trace.decision_id}


@router.get("/trade-plans/{plan_id}", response_model=dict)
def read_trade_plan(
    plan_id: str,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    require_ai_assistant_enabled(db, settings)
    plan = get_trade_plan(db, plan_id=plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Trade plan not found.")
    return {"plan": plan.model_dump(mode="json")}


@router.post("/playbooks", response_model=dict, status_code=201)
def create_playbook_api(
    payload: PlaybookCreateRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
    require_ai_assistant_enabled(db, settings)
    user_id = user.id if user is not None else None
    plan = normalize_trade_plan(payload.plan)
    payload2 = payload.model_copy(update={"plan": plan})
    pb = create_playbook(db, payload=payload2, user_id=user_id)

    trace = audit_store.new_decision_trace(
        correlation_id=_correlation_id(request),
        account_id=payload.account_id,
        user_message="playbook_create",
        inputs_used={"playbook_id": pb.playbook_id, "plan_id": pb.plan_id},
    )
    trace.final_outcome = {"type": "PLAYBOOK_CREATED", "playbook_id": pb.playbook_id}
    audit_store.persist_decision_trace(db, trace, user_id=user_id)

    return {"playbook": pb.model_dump(mode="json"), "decision_id": trace.decision_id}


@router.get("/playbooks", response_model=list)
def list_playbooks_api(
    account_id: str = "default",
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    require_ai_assistant_enabled(db, settings)
    return [p.model_dump(mode="json") for p in list_playbooks(db, account_id=account_id)]


@router.get("/playbooks/{playbook_id}", response_model=dict)
def get_playbook_api(
    playbook_id: str,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    require_ai_assistant_enabled(db, settings)
    pb = get_playbook(db, playbook_id=playbook_id)
    if pb is None:
        raise HTTPException(status_code=404, detail="Playbook not found.")
    return {"playbook": pb.model_dump(mode="json")}


@router.post("/playbooks/{playbook_id}/arm", response_model=dict)
def arm_playbook_api(
    playbook_id: str,
    request: Request,
    armed: bool,
    authorization_message_id: str | None = None,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
    require_ai_assistant_enabled(db, settings)
    require_monitoring_enabled(db, settings)
    user_id = user.id if user is not None else None
    if armed and settings.ai_execution_enabled:
        if not authorization_message_id:
            raise HTTPException(
                status_code=400,
                detail="authorization_message_id is required to arm automation when execution is enabled.",
            )
        _validate_authorization_message_id(db, message_id=authorization_message_id)
    pb = set_playbook_armed(
        db,
        playbook_id=playbook_id,
        armed=armed,
        armed_by_message_id=authorization_message_id,
    )
    if pb is None:
        raise HTTPException(status_code=404, detail="Playbook not found.")

    trace = audit_store.new_decision_trace(
        correlation_id=_correlation_id(request),
        account_id=pb.account_id,
        user_message="playbook_arm",
        inputs_used={
            "playbook_id": pb.playbook_id,
            "armed": armed,
            "authorization_message_id": authorization_message_id,
        },
    )
    trace.final_outcome = {"type": "PLAYBOOK_ARM_SET", "playbook_id": pb.playbook_id, "armed": armed}
    audit_store.persist_decision_trace(db, trace, user_id=user_id)

    return {"playbook": pb.model_dump(mode="json"), "decision_id": trace.decision_id}


@router.post("/playbooks/{playbook_id}/run-now", response_model=dict)
def run_playbook_now_api(
    playbook_id: str,
    request: Request,
    authorization_message_id: str | None = None,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
    require_ai_assistant_enabled(db, settings)
    user_id = user.id if user is not None else None

    pb = get_playbook(db, playbook_id=playbook_id)
    if pb is None:
        raise HTTPException(status_code=404, detail="Playbook not found.")
    plan = get_trade_plan(db, plan_id=pb.plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Playbook plan not found.")

    effective_auth_id = authorization_message_id or (pb.armed_by_message_id if pb.armed else None)

    corr = _correlation_id(request)
    trace = audit_store.new_decision_trace(
        correlation_id=corr,
        account_id=pb.account_id,
        user_message=f"playbook_run_now:{playbook_id}",
        inputs_used={"playbook_id": playbook_id, "plan_id": pb.plan_id},
    )

    adapter = get_broker_adapter(db, settings=settings, user_id=user_id)
    broker_snapshot = adapter.get_snapshot(account_id=pb.account_id)
    broker_snapshot = _attach_quotes(
        adapter=adapter,
        broker_snapshot=broker_snapshot,
        account_id=pb.account_id,
        symbols=plan.intent.symbols,
    )
    ledger_snapshot = build_ledger_snapshot(db, account_id=pb.account_id)
    risk = evaluate_riskgate(
        plan=plan,
        broker=broker_snapshot,
        ledger=ledger_snapshot,
        eval_ts=broker_snapshot.as_of_ts,
    )
    trace.riskgate_result = risk.decision

    outcome: Dict[str, Any] = {
        "type": "PLAYBOOK_RUN_NOW",
        "playbook_id": playbook_id,
        "plan_id": pb.plan_id,
        "risk_outcome": risk.decision.outcome.value,
        "reasons": risk.decision.reasons,
    }

    if settings.ai_execution_enabled and not settings.ai_execution_kill_switch:
        if not effective_auth_id:
            raise HTTPException(status_code=400, detail="authorization_message_id is required for execution.")
        _validate_authorization_message_id(db, message_id=effective_auth_id)
        require_execution_enabled(db, settings)
        if risk.decision.outcome.value == "allow":
            engine = ExecutionEngine()
            outcome["execution"] = engine.execute_to_broker(
                db,
                user_id=user_id,
                account_id=pb.account_id,
                correlation_id=trace.correlation_id,
                plan=plan,
                idempotency_key=f"run:{playbook_id}:{effective_auth_id}",
                broker=adapter,
            )
        else:
            outcome["execution"] = {"executed": False}
    else:
        engine = ExecutionEngine()
        dry = engine.dry_run_execute(
            db,
            user_id=user_id,
            account_id=pb.account_id,
            correlation_id=trace.correlation_id,
            plan=plan,
            idempotency_key=f"dry_run:{playbook_id}:{effective_auth_id or 'noauth'}",
        )
        outcome["execution"] = {
            "mode": "dry_run",
            "idempotency_record_id": dry.idempotency_record_id,
            "order_intents": dry.order_intents,
        }

    trace.final_outcome = outcome
    audit_store.persist_decision_trace(db, trace, user_id=user_id)
    create_playbook_run(
        db,
        playbook_id=playbook_id,
        dedupe_key=f"manual:{effective_auth_id or trace.decision_id}",
        decision_id=trace.decision_id,
        authorization_message_id=effective_auth_id,
        status="COMPLETED",
        outcome=outcome,
    )
    touch_playbook_after_run(db, playbook_id=playbook_id)
    return {"decision_id": trace.decision_id, "outcome": outcome}


@router.get("/playbooks/{playbook_id}/runs", response_model=list)
def list_playbook_runs_api(
    playbook_id: str,
    limit: int = 50,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    require_ai_assistant_enabled(db, settings)
    runs = list_playbook_runs(db, playbook_id=playbook_id, limit=limit)
    return [r.model_dump(mode="json") for r in runs]


@router.get("/portfolio/diagnostics", response_model=PortfolioDiagnostics)
def portfolio_diagnostics_api(
    request: Request,
    account_id: str = "default",
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
) -> PortfolioDiagnostics:
    require_ai_assistant_enabled(db, settings)
    user_id = user.id if user is not None else None
    adapter = get_broker_adapter(db, settings=settings, user_id=user_id)
    broker_snapshot = adapter.get_snapshot(account_id=account_id)
    ledger_snapshot = build_ledger_snapshot(db, account_id=account_id)
    symbols = sorted(
        {
            str(p.symbol).upper()
            for p in (broker_snapshot.positions or [])
        }
        | {
            str(p.symbol).upper()
            for p in (ledger_snapshot.expected_positions or [])
        }
    )
    broker_snapshot = _attach_quotes(
        adapter=adapter,
        broker_snapshot=broker_snapshot,
        account_id=account_id,
        symbols=symbols,
    )
    diag = build_portfolio_diagnostics(
        db,
        account_id=account_id,
        broker_snapshot=broker_snapshot,
        ledger_snapshot=ledger_snapshot,
    )

    trace = audit_store.new_decision_trace(
        correlation_id=_correlation_id(request),
        account_id=account_id,
        user_message="portfolio_diagnostics",
        inputs_used={"adapter": adapter.name},
    )
    trace.final_outcome = {
        "type": "PORTFOLIO_DIAGNOSTICS",
        "drift_count": len(diag.drift),
        "corr_status": diag.correlation.get("status"),
    }
    audit_store.persist_decision_trace(db, trace, user_id=user_id)
    return diag


@router.get("/market-context", response_model=MarketContextResponse)
def market_context_api(
    request: Request,
    symbols: str,
    account_id: str = "default",
    exchange: str = "NSE",
    timeframe: str = "1d",
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
) -> MarketContextResponse:
    require_ai_assistant_enabled(db, settings)
    user_id = user.id if user is not None else None
    symbols_list = [s.strip().upper() for s in (symbols or "").split(",") if s.strip()]
    overlay = build_market_context_overlay(db, symbols=symbols_list, exchange=exchange, timeframe=timeframe)

    trace = audit_store.new_decision_trace(
        correlation_id=_correlation_id(request),
        account_id=account_id,
        user_message="market_context",
        inputs_used={"symbols": symbols_list, "exchange": exchange, "timeframe": timeframe},
    )
    trace.final_outcome = {"type": "MARKET_CONTEXT", "symbols": len(symbols_list)}
    audit_store.persist_decision_trace(db, trace, user_id=user_id)

    return MarketContextResponse(overlay=overlay)


@router.post("/sizing/suggest", response_model=SizingSuggestResponse)
def sizing_suggest_api(
    payload: SizingSuggestRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
) -> SizingSuggestResponse:
    require_ai_assistant_enabled(db, settings)
    user_id = user.id if user is not None else None

    equity_value = payload.equity_value
    notes: List[str] = []
    if equity_value is None:
        adapter = get_broker_adapter(db, settings=settings, user_id=user_id)
        snap = adapter.get_snapshot(account_id=payload.account_id)
        equity_value = extract_equity_value(dict(snap.margins or {}))
        if equity_value is None:
            raise HTTPException(
                status_code=400,
                detail="equity_value is required (unable to infer from broker margins).",
            )
        notes.append(f"equity_inferred_from:{adapter.name}")

    try:
        suggested_qty, metrics = suggest_qty(
            entry_price=float(payload.entry_price),
            stop_price=float(payload.stop_price),
            risk_budget_pct=float(payload.risk_budget_pct),
            equity_value=float(equity_value),
            max_qty=payload.max_qty,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    trace = audit_store.new_decision_trace(
        correlation_id=_correlation_id(request),
        account_id=payload.account_id,
        user_message="sizing_suggest",
        inputs_used={
            "symbol": payload.symbol,
            "exchange": payload.exchange,
            "entry_price": payload.entry_price,
            "stop_price": payload.stop_price,
            "risk_budget_pct": payload.risk_budget_pct,
            "equity_value": float(equity_value),
        },
    )
    trace.final_outcome = {"type": "SIZING_SUGGEST", "suggested_qty": suggested_qty}
    audit_store.persist_decision_trace(db, trace, user_id=user_id)

    return SizingSuggestResponse(
        symbol=payload.symbol.strip().upper(),
        exchange=payload.exchange.strip().upper(),
        entry_price=float(payload.entry_price),
        stop_price=float(payload.stop_price),
        risk_budget_pct=float(payload.risk_budget_pct),
        equity_value=float(equity_value),
        risk_per_share=float(metrics["risk_per_share"]),
        risk_amount=float(metrics["risk_amount"]),
        suggested_qty=int(suggested_qty),
        notional_value=float(metrics["notional_value"]),
        notes=notes,
    )
