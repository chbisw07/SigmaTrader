from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.api.orders import execute_order_internal
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import Order, RebalanceRun, RebalanceRunOrder, User
from app.schemas.rebalance import (
    RebalanceExecuteRequest,
    RebalanceExecuteResponse,
    RebalanceExecuteResult,
    RebalancePreviewRequest,
    RebalancePreviewResponse,
    RebalanceRunRead,
)
from app.services.rebalance import _broker_list, build_run_snapshots, preview_rebalance

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


def _now_utc() -> datetime:
    return datetime.now(UTC)


@router.post("/preview", response_model=RebalancePreviewResponse)
def rebalance_preview(
    payload: RebalancePreviewRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> RebalancePreviewResponse:
    results = preview_rebalance(db, settings, user=user, req=payload)
    return RebalancePreviewResponse(results=results)


@router.post("/execute", response_model=RebalanceExecuteResponse)
def rebalance_execute(
    payload: RebalanceExecuteRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> RebalanceExecuteResponse:
    brokers = _broker_list(payload.broker_name)

    results: list[RebalanceExecuteResult] = []
    for broker in brokers:
        if payload.target_kind == "HOLDINGS":
            preview_req = RebalancePreviewRequest(
                target_kind="HOLDINGS",
                group_id=None,
                broker_name=broker,  # type: ignore[arg-type]
                budget_pct=payload.budget_pct,
                budget_amount=payload.budget_amount,
                drift_band_abs_pct=payload.drift_band_abs_pct,
                drift_band_rel_pct=payload.drift_band_rel_pct,
                max_trades=payload.max_trades,
                min_trade_value=payload.min_trade_value,
            )
            previews = preview_rebalance(db, settings, user=user, req=preview_req)
            if not previews:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Preview did not produce a result.",
                )
            preview = previews[0]

            created_order_ids: list[int] = []
            for trade in preview.trades:
                order = Order(
                    user_id=user.id,
                    broker_name=broker,
                    alert_id=None,
                    strategy_id=None,
                    symbol=trade.symbol,
                    exchange=trade.exchange,
                    side=trade.side,
                    qty=float(trade.qty),
                    price=(
                        float(trade.estimated_price)
                        if payload.order_type == "LIMIT"
                        else None
                    ),
                    trigger_price=None,
                    trigger_percent=None,
                    order_type=payload.order_type,
                    product=payload.product,
                    gtt=False,
                    synthetic_gtt=False,
                    armed_at=None,
                    status="WAITING",
                    mode=payload.mode,
                    execution_target=payload.execution_target,
                    simulated=False,
                    created_at=_now_utc(),
                )
                db.add(order)
                db.commit()
                db.refresh(order)
                created_order_ids.append(int(order.id))

                if payload.mode == "AUTO":
                    try:
                        execute_order_internal(
                            order_id=order.id,
                            request=request,
                            db=db,
                            settings=settings,
                        )
                        db.refresh(order)
                    except HTTPException as exc:
                        db.refresh(order)
                        if order.status == "WAITING":
                            order.status = "FAILED"
                            order.error_message = (
                                exc.detail
                                if isinstance(exc.detail, str)
                                else str(exc.detail)
                            )
                            db.add(order)
                            db.commit()
                            db.refresh(order)
                    except Exception as exc:  # pragma: no cover - defensive
                        db.refresh(order)
                        if order.status == "WAITING":
                            order.status = "FAILED"
                            order.error_message = str(exc)
                            db.add(order)
                            db.commit()
                            db.refresh(order)

            results.append(
                RebalanceExecuteResult(run=None, created_order_ids=created_order_ids)
            )
            continue

        idem = payload.idempotency_key
        if idem and len(brokers) > 1:
            idem = f"{idem}:{broker}"

        if idem:
            existing: RebalanceRun | None = (
                db.query(RebalanceRun)
                .filter(
                    RebalanceRun.owner_id == user.id,
                    RebalanceRun.idempotency_key == idem,
                )
                .one_or_none()
            )
            if existing is not None:
                created = [
                    o.order_id for o in existing.orders if o.order_id is not None
                ]
                results.append(
                    RebalanceExecuteResult(
                        run=RebalanceRunRead.from_orm(existing),
                        created_order_ids=[int(x) for x in created],
                    )
                )
                continue

        preview_req = RebalancePreviewRequest(
            target_kind="GROUP",
            group_id=payload.group_id,
            broker_name=broker,  # type: ignore[arg-type]
            budget_pct=payload.budget_pct,
            budget_amount=payload.budget_amount,
            drift_band_abs_pct=payload.drift_band_abs_pct,
            drift_band_rel_pct=payload.drift_band_rel_pct,
            max_trades=payload.max_trades,
            min_trade_value=payload.min_trade_value,
        )
        previews = preview_rebalance(db, settings, user=user, req=preview_req)
        if not previews:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Preview did not produce a result.",
            )
        preview = previews[0]

        policy_json, inputs_json, summary_json = build_run_snapshots(
            req=preview_req,
            preview=preview,
        )

        run = RebalanceRun(
            owner_id=user.id,
            group_id=int(payload.group_id or 0),
            broker_name=broker,
            status="CREATED",
            mode=payload.mode,
            idempotency_key=idem,
            policy_snapshot_json=policy_json,
            inputs_snapshot_json=inputs_json,
            summary_json=summary_json,
            created_at=_now_utc(),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        created_order_ids: list[int] = []
        try:
            for trade in preview.trades:
                ro = RebalanceRunOrder(
                    run_id=run.id,
                    order_id=None,
                    symbol=trade.symbol,
                    exchange=trade.exchange,
                    side=trade.side,
                    qty=float(trade.qty),
                    estimated_price=float(trade.estimated_price),
                    estimated_notional=float(trade.estimated_notional),
                    target_weight=float(trade.target_weight),
                    live_weight=float(trade.live_weight),
                    drift=float(trade.drift),
                    current_value=float(trade.current_value),
                    desired_value=float(trade.desired_value),
                    delta_value=float(trade.delta_value),
                    scale=float(trade.scale),
                    reason_json=json.dumps(
                        trade.reason, ensure_ascii=False, separators=(",", ":")
                    ),
                    status="PROPOSED",
                    created_at=_now_utc(),
                )
                db.add(ro)
                db.commit()
                db.refresh(ro)

                order = Order(
                    user_id=user.id,
                    broker_name=broker,
                    alert_id=None,
                    strategy_id=None,
                    symbol=trade.symbol,
                    exchange=trade.exchange,
                    side=trade.side,
                    qty=float(trade.qty),
                    price=(
                        float(trade.estimated_price)
                        if payload.order_type == "LIMIT"
                        else None
                    ),
                    trigger_price=None,
                    trigger_percent=None,
                    order_type=payload.order_type,
                    product=payload.product,
                    gtt=False,
                    synthetic_gtt=False,
                    armed_at=None,
                    status="WAITING",
                    mode=payload.mode,
                    execution_target=payload.execution_target,
                    simulated=False,
                    created_at=_now_utc(),
                )
                db.add(order)
                db.commit()
                db.refresh(order)

                ro.order_id = order.id
                ro.status = "ORDER_CREATED"
                db.add(ro)
                db.commit()
                db.refresh(ro)

                created_order_ids.append(int(order.id))

                if payload.mode == "AUTO":
                    try:
                        execute_order_internal(
                            order_id=order.id,
                            request=request,
                            db=db,
                            settings=settings,
                        )
                        db.refresh(order)
                    except HTTPException as exc:
                        db.refresh(order)
                        if order.status == "WAITING":
                            order.status = "FAILED"
                            order.error_message = (
                                exc.detail
                                if isinstance(exc.detail, str)
                                else str(exc.detail)
                            )
                            db.add(order)
                            db.commit()
                            db.refresh(order)
                    except Exception as exc:  # pragma: no cover - defensive
                        db.refresh(order)
                        if order.status == "WAITING":
                            order.status = "FAILED"
                            order.error_message = str(exc)
                            db.add(order)
                            db.commit()
                            db.refresh(order)

            run.status = "EXECUTED"
            run.executed_at = _now_utc()
            db.add(run)
            db.commit()
            db.refresh(run)
        except Exception as exc:
            run.status = "FAILED"
            run.error_message = str(exc)
            db.add(run)
            db.commit()
            db.refresh(run)
            raise

        results.append(
            RebalanceExecuteResult(
                run=RebalanceRunRead.from_orm(run),
                created_order_ids=created_order_ids,
            )
        )

    return RebalanceExecuteResponse(results=results)


@router.get("/runs", response_model=List[RebalanceRunRead])
def list_rebalance_runs(
    group_id: Annotated[Optional[int], Query(ge=1)] = None,
    broker_name: Annotated[Optional[str], Query()] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[RebalanceRunRead]:
    q = db.query(RebalanceRun).filter(RebalanceRun.owner_id == user.id)
    if group_id is not None:
        q = q.filter(RebalanceRun.group_id == group_id)
    if broker_name is not None:
        b = (broker_name or "").strip().lower()
        if b in {"zerodha", "angelone"}:
            q = q.filter(RebalanceRun.broker_name == b)
    rows = q.order_by(RebalanceRun.created_at.desc()).limit(200).all()
    return [RebalanceRunRead.from_orm(r) for r in rows]


@router.get("/runs/{run_id}", response_model=RebalanceRunRead)
def get_rebalance_run(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RebalanceRunRead:
    run: RebalanceRun | None = (
        db.query(RebalanceRun)
        .filter(RebalanceRun.id == run_id, RebalanceRun.owner_id == user.id)
        .one_or_none()
    )
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return RebalanceRunRead.from_orm(run)


__all__ = ["router"]
