from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import (
    Group,
    GroupMember,
    ScreenerRun,
    SignalStrategy,
    SignalStrategyVersion,
    User,
)
from app.schemas.alerts_v3 import AlertVariableDef
from app.schemas.groups import GroupMemberCreate, GroupRead
from app.schemas.screener_v3 import (
    ScreenerCleanupResponse,
    ScreenerCreateGroupRequest,
    ScreenerRow,
    ScreenerRunRead,
    ScreenerRunRequest,
    ScreenerRunsCleanupRequest,
)
from app.services.indicator_alerts import IndicatorAlertError
from app.services.screener_v3 import (
    create_screener_run,
    evaluate_screener_v3,
    resolve_screener_targets,
    start_screener_run_async,
)
from app.services.signal_strategies import (
    load_inputs,
    load_outputs,
    load_variables,
    materialize_params,
    pick_default_signal_output,
    pick_output,
)

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


def _model_validate(schema_cls, obj):
    """Compat helper for Pydantic v1/v2."""

    if hasattr(schema_cls, "model_validate"):
        return schema_cls.model_validate(obj)  # type: ignore[attr-defined]
    return schema_cls.from_orm(obj)  # type: ignore[call-arg]


def _rows_from_json(raw: str) -> list[ScreenerRow]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    out: list[ScreenerRow] = []
    for item in parsed:
        if isinstance(item, dict):
            out.append(ScreenerRow(**item))
    return out


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _run_to_read(run: ScreenerRun, *, include_rows: bool) -> ScreenerRunRead:
    rows = _rows_from_json(run.results_json) if include_rows else None
    include_holdings = False
    group_ids: list[int] = []
    try:
        target = json.loads(run.target_json or "{}")
        if isinstance(target, dict):
            include_holdings = bool(target.get("include_holdings"))
            group_ids = [int(x) for x in (target.get("group_ids") or [])]
    except Exception:
        include_holdings = False
        group_ids = []

    variables = []
    try:
        parsed_vars = json.loads(run.variables_json or "[]")
        if isinstance(parsed_vars, list):
            for item in parsed_vars:
                if isinstance(item, dict):
                    variables.append(AlertVariableDef(**item))
    except Exception:
        variables = []

    params: dict = {}
    try:
        parsed = json.loads(getattr(run, "signal_strategy_params_json", "") or "{}")
        if isinstance(parsed, dict):
            params = parsed
    except Exception:
        params = {}
    return ScreenerRunRead(
        id=run.id,
        status=run.status,
        evaluation_cadence=run.evaluation_cadence,
        total_symbols=run.total_symbols,
        evaluated_symbols=run.evaluated_symbols,
        matched_symbols=run.matched_symbols,
        missing_symbols=run.missing_symbols,
        error=run.error,
        started_at=_ensure_utc(run.started_at),
        finished_at=_ensure_utc(run.finished_at),
        created_at=_ensure_utc(run.created_at) or datetime.now(UTC),
        include_holdings=include_holdings,
        group_ids=group_ids,
        variables=variables,
        condition_dsl=run.condition_dsl or "",
        rows=rows,
        signal_strategy_version_id=getattr(run, "signal_strategy_version_id", None),
        signal_strategy_output=getattr(run, "signal_strategy_output", None),
        signal_strategy_params=params,
    )


def _get_strategy_version_or_404(
    db: Session, *, user_id: int, version_id: int
) -> SignalStrategyVersion:
    v = db.get(SignalStrategyVersion, version_id)
    if v is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    s = db.get(SignalStrategy, v.strategy_id)
    if s is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if (
        getattr(s, "scope", "USER") or "USER"
    ).upper() == "USER" and s.owner_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return v


@router.post("/run", response_model=ScreenerRunRead)
def run_screener(
    payload: ScreenerRunRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> ScreenerRunRead:
    variables = payload.variables
    text = (payload.condition_dsl or "").strip()
    strategy_version_id = payload.signal_strategy_version_id
    strategy_output = payload.signal_strategy_output
    strategy_params_json = json.dumps(payload.signal_strategy_params or {}, default=str)
    params = payload.signal_strategy_params or {}

    if strategy_version_id is not None:
        try:
            v = _get_strategy_version_or_404(
                db, user_id=user.id, version_id=int(strategy_version_id)
            )
            inputs = load_inputs(getattr(v, "inputs_json", "[]") or "[]")
            variables = load_variables(getattr(v, "variables_json", "[]") or "[]")
            outputs = load_outputs(getattr(v, "outputs_json", "[]") or "[]")
            out = (
                pick_output(outputs, name=strategy_output, require_kind="SIGNAL")
                if strategy_output
                else pick_default_signal_output(outputs)
            )
            params = materialize_params(inputs=inputs, overrides=params)
            strategy_params_json = json.dumps(params, default=str)
            strategy_output = out.name
            text = (out.dsl or "").strip()
        except IndicatorAlertError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc

    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Condition DSL cannot be empty.",
        )

    targets = resolve_screener_targets(
        db,
        settings,
        user=user,
        include_holdings=payload.include_holdings,
        group_ids=payload.group_ids,
    )
    total = len(targets)

    # Persist a run record even for synchronous runs so the UI can re-open and
    # (optionally) create a group from matches using the same run_id.
    variables_json = json.dumps(
        [v.model_dump() if hasattr(v, "model_dump") else v.dict() for v in variables],
        default=str,
    )
    run = create_screener_run(
        db,
        user=user,
        include_holdings=payload.include_holdings,
        group_ids=payload.group_ids,
        variables_json=variables_json,
        condition_dsl=text,
        evaluation_cadence=(payload.evaluation_cadence or "").strip() or "1m",
        total_symbols=total,
        signal_strategy_version_id=(
            int(strategy_version_id) if strategy_version_id is not None else None
        ),
        signal_strategy_output=strategy_output,
        signal_strategy_params_json=strategy_params_json,
    )

    # Hybrid execution: do a blocking run for small universes; async otherwise.
    sync_limit = max(int(settings.screener_sync_limit or 0), 0)
    if total <= sync_limit:
        try:
            rows, cadence, stats = evaluate_screener_v3(
                db,
                settings,
                user=user,
                include_holdings=payload.include_holdings,
                group_ids=payload.group_ids,
                variables=variables,
                condition_dsl=text,
                evaluation_cadence=payload.evaluation_cadence,
                params=params,
                allow_fetch=False,
            )
        except Exception as exc:
            run.status = "ERROR"
            run.error = str(exc)
            run.finished_at = datetime.now(UTC)
            db.add(run)
            db.commit()
            return _run_to_read(run, include_rows=True)

        run.status = "DONE"
        run.evaluation_cadence = cadence
        run.evaluated_symbols = stats["evaluated_symbols"]
        run.matched_symbols = stats["matched_symbols"]
        run.missing_symbols = stats["missing_symbols"]
        run.results_json = json.dumps(
            [r.model_dump() if hasattr(r, "model_dump") else r.dict() for r in rows],
            default=str,
        )
        run.finished_at = datetime.now(UTC)
        db.add(run)
        db.commit()
        db.refresh(run)
        return _run_to_read(run, include_rows=True)

    start_screener_run_async(run.id)
    return _run_to_read(run, include_rows=False)


@router.get("/runs/{run_id}", response_model=ScreenerRunRead)
def get_screener_run(
    run_id: int,
    include_rows: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScreenerRunRead:
    run = db.get(ScreenerRun, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return _run_to_read(run, include_rows=include_rows)


@router.post("/runs/{run_id}/create-group", response_model=GroupRead)
def create_group_from_run(
    run_id: int,
    payload: ScreenerCreateGroupRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GroupRead:
    run = db.get(ScreenerRun, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if run.status != "DONE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Run is not complete yet.",
        )

    rows = _rows_from_json(run.results_json)
    members = [
        GroupMemberCreate(symbol=r.symbol, exchange=r.exchange)
        for r in rows
        if r.matched
    ]
    if not members:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No matches found; group not created.",
        )

    group = Group(
        owner_id=user.id,
        name=payload.name,
        kind=payload.kind,
        description=payload.description,
    )
    db.add(group)
    db.flush()

    # Bulk insert members.
    created = [
        GroupMember(
            group_id=group.id,
            symbol=m.symbol,
            exchange=m.exchange,
        )
        for m in members
    ]
    db.add_all(created)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to add group members: {exc}",
        ) from exc
    db.refresh(group)

    result = _model_validate(GroupRead, group)
    result.member_count = len(created)
    return result


@router.get("/runs", response_model=list[ScreenerRunRead])
def list_screener_runs(
    limit: int = Query(25, ge=1, le=500),
    offset: int = Query(0, ge=0),
    include_rows: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ScreenerRunRead]:
    runs = (
        db.query(ScreenerRun)
        .filter(ScreenerRun.user_id == user.id)
        .order_by(ScreenerRun.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_run_to_read(r, include_rows=include_rows) for r in runs]


@router.delete(
    "/runs/{run_id}",
    status_code=204,
    response_class=Response,
    response_model=None,
)
def delete_screener_run(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    run = db.get(ScreenerRun, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    db.delete(run)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/runs/cleanup", response_model=ScreenerCleanupResponse)
def cleanup_screener_runs(
    payload: ScreenerRunsCleanupRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScreenerCleanupResponse:
    """Delete old runs according to retention policy.

    Rules are applied in this order:
    1) If max_days is set: delete runs older than now - max_days.
    2) If max_runs is set: keep newest max_runs runs, delete the rest.
    """

    deleted = 0

    if payload.max_days is not None:
        cutoff = datetime.now(UTC) - payload.max_days_delta()
        q = db.query(ScreenerRun).filter(
            ScreenerRun.user_id == user.id, ScreenerRun.created_at < cutoff
        )
        if payload.dry_run:
            deleted += q.count()
        else:
            deleted += q.delete(synchronize_session=False)
            db.commit()

    if payload.max_runs is not None:
        ids = (
            db.query(ScreenerRun.id)
            .filter(ScreenerRun.user_id == user.id)
            .order_by(ScreenerRun.created_at.desc())
            .offset(int(payload.max_runs))
            .all()
        )
        old_ids = [int(r[0]) for r in ids]
        if old_ids:
            if payload.dry_run:
                deleted += len(old_ids)
            else:
                deleted += (
                    db.query(ScreenerRun)
                    .filter(ScreenerRun.user_id == user.id, ScreenerRun.id.in_(old_ids))
                    .delete(synchronize_session=False)
                )
                db.commit()

    remaining = db.query(ScreenerRun).filter(ScreenerRun.user_id == user.id).count()
    return ScreenerCleanupResponse(deleted=deleted, remaining=remaining)


__all__ = ["router"]
