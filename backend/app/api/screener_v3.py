from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import Group, GroupMember, ScreenerRun, User
from app.schemas.groups import GroupMemberCreate, GroupRead
from app.schemas.screener_v3 import (
    ScreenerCreateGroupRequest,
    ScreenerRow,
    ScreenerRunRead,
    ScreenerRunRequest,
)
from app.services.screener_v3 import (
    create_screener_run,
    evaluate_screener_v3,
    resolve_screener_targets,
    start_screener_run_async,
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


def _run_to_read(run: ScreenerRun, *, include_rows: bool) -> ScreenerRunRead:
    rows = _rows_from_json(run.results_json) if include_rows else None
    return ScreenerRunRead(
        id=run.id,
        status=run.status,
        evaluation_cadence=run.evaluation_cadence,
        total_symbols=run.total_symbols,
        evaluated_symbols=run.evaluated_symbols,
        matched_symbols=run.matched_symbols,
        missing_symbols=run.missing_symbols,
        error=run.error,
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_at=run.created_at,
        rows=rows,
    )


@router.post("/run", response_model=ScreenerRunRead)
def run_screener(
    payload: ScreenerRunRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> ScreenerRunRead:
    text = (payload.condition_dsl or "").strip()
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
        [
            v.model_dump() if hasattr(v, "model_dump") else v.dict()
            for v in payload.variables
        ],
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
                variables=payload.variables,
                condition_dsl=text,
                evaluation_cadence=payload.evaluation_cadence,
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


__all__ = ["router"]
