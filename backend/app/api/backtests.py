from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.auth import get_current_user_optional
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import BacktestRun, User
from app.schemas.backtests import (
    BacktestRunCreate,
    BacktestRunRead,
    EodCandleLoadRequest,
    EodCandleLoadResponse,
)
from app.schemas.backtests_signal import SignalBacktestConfigIn
from app.services.backtests_data import _norm_symbol_ref, load_eod_close_matrix
from app.services.backtests_signal import SignalBacktestConfig, run_signal_backtest

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
    if kind not in {"SIGNAL", "PORTFOLIO", "EXECUTION"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="kind must be SIGNAL, PORTFOLIO, or EXECUTION.",
        )
    title = payload.title.strip() if payload.title and payload.title.strip() else None

    cfg_in: SignalBacktestConfigIn | None = None
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

    config = {
        "kind": kind,
        "title": title,
        "universe": payload.universe.dict(),
        "config": payload.config,
    }
    now = datetime.now(UTC)
    status_val = "RUNNING" if kind == "SIGNAL" else "PENDING"
    run = BacktestRun(
        owner_id=user.id if user is not None else None,
        kind=kind,
        status=status_val,
        title=title,
        config_json=json.dumps(config, ensure_ascii=False),
        result_json=None,
        error_message=None,
        started_at=now if kind == "SIGNAL" else None,
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

        if kind == "SIGNAL":
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


__all__ = ["router"]
