from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.auth import get_current_user, get_current_user_optional
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import BacktestRun, User
from app.schemas.backtests import (
    BacktestRunCreate,
    BacktestRunRead,
    BacktestRunsDeleteRequest,
    BacktestRunsDeleteResponse,
    EodCandleLoadRequest,
    EodCandleLoadResponse,
)
from app.schemas.backtests_portfolio import PortfolioBacktestConfigIn
from app.schemas.backtests_signal import SignalBacktestConfigIn
from app.schemas.backtests_strategy import StrategyBacktestConfigIn
from app.services.backtests_data import _norm_symbol_ref, load_eod_close_matrix
from app.services.backtests_execution import run_execution_backtest
from app.services.backtests_portfolio import run_portfolio_backtest
from app.services.backtests_signal import SignalBacktestConfig, run_signal_backtest
from app.services.backtests_strategy import run_strategy_backtest

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


@router.post("/runs", response_model=BacktestRunRead)
def create_backtest_run(
    payload: BacktestRunCreate,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
    settings: Settings = Depends(get_settings),
) -> BacktestRunRead:
    kind = (payload.kind or "").strip().upper()
    if kind not in {"SIGNAL", "PORTFOLIO", "EXECUTION", "STRATEGY"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="kind must be SIGNAL, PORTFOLIO, EXECUTION, or STRATEGY.",
        )
    title = payload.title.strip() if payload.title and payload.title.strip() else None

    cfg_in: SignalBacktestConfigIn | None = None
    pf_cfg_in: PortfolioBacktestConfigIn | None = None
    st_cfg_in: StrategyBacktestConfigIn | None = None
    exec_cfg_in = None
    if kind == "SIGNAL":
        try:
            cfg_in = SignalBacktestConfigIn.parse_obj(payload.config)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid SIGNAL backtest config: {exc}",
            ) from exc
        if cfg_in.mode == "DSL" and not (cfg_in.dsl or "").strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="DSL is required for SIGNAL backtest mode DSL.",
            )
    elif kind == "PORTFOLIO":
        try:
            pf_cfg_in = PortfolioBacktestConfigIn.parse_obj(payload.config)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid PORTFOLIO backtest config: {exc}",
            ) from exc
        if pf_cfg_in.method not in {"TARGET_WEIGHTS", "ROTATION", "RISK_PARITY"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only TARGET_WEIGHTS/ROTATION/RISK_PARITY are supported.",
            )
        if payload.universe.group_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="PORTFOLIO backtests require universe.group_id.",
            )
    elif kind == "STRATEGY":
        try:
            st_cfg_in = StrategyBacktestConfigIn.parse_obj(payload.config)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid STRATEGY backtest config: {exc}",
            ) from exc
        if len(payload.universe.symbols) != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="STRATEGY backtests require exactly one universe.symbols entry.",
            )
        entry_ok = bool((st_cfg_in.entry_dsl or "").strip())
        exit_ok = bool((st_cfg_in.exit_dsl or "").strip())
        if not entry_ok or not exit_ok:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="entry_dsl and exit_dsl are required for STRATEGY backtests.",
            )
    else:
        from app.schemas.backtests_execution import ExecutionBacktestConfigIn

        try:
            exec_cfg_in = ExecutionBacktestConfigIn.parse_obj(payload.config)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid EXECUTION backtest config: {exc}",
            ) from exc

        base_run = db.get(BacktestRun, int(exec_cfg_in.base_run_id))
        if base_run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="base_run_id not found.",
            )
        if user is None:
            if base_run.owner_id is not None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="base_run_id not found.",
                )
        else:
            if base_run.owner_id not in (None, user.id):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="base_run_id not found.",
                )
        if base_run.kind != "PORTFOLIO":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="base_run_id must reference a PORTFOLIO backtest run.",
            )
        if base_run.status != "COMPLETED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="base_run_id must reference a COMPLETED run.",
            )

    config = {
        "kind": kind,
        "title": title,
        "universe": payload.universe.dict(),
        "config": payload.config,
    }
    now = datetime.now(UTC)
    status_val = "RUNNING"
    run = BacktestRun(
        owner_id=user.id if user is not None else None,
        kind=kind,
        status=status_val,
        title=title,
        config_json=json.dumps(config, ensure_ascii=False),
        result_json=None,
        error_message=None,
        started_at=now,
        finished_at=None,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        result: dict | None = None
        if kind == "SIGNAL":
            assert cfg_in is not None
            sym_refs = [
                _norm_symbol_ref(s.exchange, s.symbol) for s in payload.universe.symbols
            ]
            cfg = SignalBacktestConfig(
                mode=cfg_in.mode,
                start_date=cfg_in.start_date,
                end_date=cfg_in.end_date,
                forward_windows=cfg_in.forward_windows,
                dsl=cfg_in.dsl,
                ranking_metric=cfg_in.ranking_metric,
                ranking_window=cfg_in.ranking_window,
                top_n=cfg_in.top_n,
                cadence=cfg_in.cadence,
            )
            result = run_signal_backtest(
                db,
                settings,
                symbols=sym_refs,
                config=cfg,
                allow_fetch=True,
            )
        elif kind == "PORTFOLIO":
            assert pf_cfg_in is not None
            group_id = int(payload.universe.group_id)
            result = run_portfolio_backtest(
                db,
                settings,
                group_id=group_id,
                config=pf_cfg_in,
                allow_fetch=True,
            )
        elif kind == "EXECUTION":
            assert exec_cfg_in is not None
            base_run = db.get(BacktestRun, int(exec_cfg_in.base_run_id))
            assert base_run is not None
            result = run_execution_backtest(
                db,
                settings,
                base_run=base_run,
                config=exec_cfg_in,
                allow_fetch=True,
            )
        elif kind == "STRATEGY":
            assert st_cfg_in is not None
            sym = payload.universe.symbols[0]
            sym_ref = _norm_symbol_ref(sym.exchange, sym.symbol)
            result = run_strategy_backtest(
                db,
                settings,
                symbol=sym_ref,
                config=payload.config,
                allow_fetch=True,
            )

        run.status = "COMPLETED"
        run.finished_at = datetime.now(UTC)
        run.result_json = json.dumps(result, ensure_ascii=False) if result else None
        db.add(run)
        db.commit()
        db.refresh(run)
    except Exception as exc:
        run.status = "FAILED"
        run.finished_at = datetime.now(UTC)
        run.error_message = str(exc)
        db.add(run)
        db.commit()
        db.refresh(run)

    return BacktestRunRead.from_model(run)


@router.get("/runs", response_model=List[BacktestRunRead])
def list_backtest_runs(
    kind: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> List[BacktestRunRead]:
    q = db.query(BacktestRun)
    if user is not None:
        q = q.filter(
            (BacktestRun.owner_id == user.id) | (BacktestRun.owner_id.is_(None))
        )
    else:
        q = q.filter(BacktestRun.owner_id.is_(None))
    if kind:
        q = q.filter(BacktestRun.kind == kind.strip().upper())
    rows = q.order_by(BacktestRun.created_at.desc()).limit(limit).all()
    return [BacktestRunRead.from_model(r) for r in rows]


@router.get("/runs/{run_id}", response_model=BacktestRunRead)
def get_backtest_run(
    run_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> BacktestRunRead:
    run = db.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if user is None:
        if run.owner_id is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Not found"
            )
    else:
        if run.owner_id not in (None, user.id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Not found"
            )
    return BacktestRunRead.from_model(run)


@router.post("/candles/eod", response_model=EodCandleLoadResponse)
def load_eod_candles(
    payload: EodCandleLoadRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_current_user_optional),
) -> EodCandleLoadResponse:
    _ = user  # Best-effort; candles are not user-specific today.
    symbols = [_norm_symbol_ref(s.exchange, s.symbol) for s in (payload.symbols or [])]
    dates, matrix, missing = load_eod_close_matrix(
        db,
        settings,
        symbols=symbols,
        start=payload.start,
        end=payload.end,
        allow_fetch=payload.allow_fetch,
    )
    return EodCandleLoadResponse(
        dates=[d.isoformat() for d in dates],
        prices=matrix,
        missing_symbols=missing,
    )


@router.delete("/runs", response_model=BacktestRunsDeleteResponse)
def delete_backtest_runs(
    payload: BacktestRunsDeleteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BacktestRunsDeleteResponse:
    ids_in = [int(x) for x in (payload.ids or []) if int(x) > 0]
    ids = sorted(set(ids_in))
    if not ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ids is required.",
        )

    rows = db.query(BacktestRun).filter(BacktestRun.id.in_(ids)).all()
    by_id = {r.id: r for r in rows}

    deleted: list[int] = []
    forbidden: list[int] = []
    missing: list[int] = []

    for rid in ids:
        run = by_id.get(rid)
        if run is None:
            missing.append(rid)
            continue
        allowed = user.role == "ADMIN" or run.owner_id in (None, user.id)
        if not allowed:
            forbidden.append(rid)
            continue
        db.delete(run)
        deleted.append(rid)

    db.commit()
    return BacktestRunsDeleteResponse(
        deleted_ids=deleted,
        forbidden_ids=forbidden,
        missing_ids=missing,
    )


__all__ = ["router"]
