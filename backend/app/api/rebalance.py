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
from app.models import (
    Group,
    Order,
    RebalancePolicy,
    RebalanceRun,
    RebalanceRunOrder,
    RebalanceSchedule,
    User,
)
from app.schemas.rebalance import (
    RebalanceExecuteRequest,
    RebalanceExecuteResponse,
    RebalanceExecuteResult,
    RebalancePreviewRequest,
    RebalancePreviewResponse,
    RebalanceRunRead,
)
from app.schemas.rebalance_schedule import (
    RebalanceScheduleConfig,
    RebalanceScheduleRead,
    RebalanceScheduleUpdate,
)
from app.services.price_ticks import round_price_to_tick
from app.services.rebalance import _broker_list, build_run_snapshots, preview_rebalance
from app.services.rebalance_schedule import (
    _json_load,
    compute_next_rebalance_at,
    normalize_schedule_config,
    schedule_config_to_json,
)

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _get_group_or_404(db: Session, group_id: int) -> Group:
    g = db.get(Group, group_id)
    if g is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return g


def _ensure_policy_and_schedule(
    db: Session,
    *,
    user_id: int,
    group_id: int,
) -> tuple[RebalancePolicy, RebalanceSchedule]:
    policy: RebalancePolicy | None = (
        db.query(RebalancePolicy)
        .filter(
            RebalancePolicy.owner_id == user_id, RebalancePolicy.group_id == group_id
        )
        .one_or_none()
    )
    if policy is None:
        policy = RebalancePolicy(
            owner_id=user_id,
            group_id=group_id,
            name="default",
            enabled=True,
            broker_scope="zerodha",
            policy_json=None,
        )
        db.add(policy)
        db.commit()
        db.refresh(policy)

    sched: RebalanceSchedule | None = (
        db.query(RebalanceSchedule)
        .filter(RebalanceSchedule.policy_id == policy.id)
        .one_or_none()
    )
    if sched is None:
        cfg = normalize_schedule_config({})
        next_at = compute_next_rebalance_at(cfg=cfg)
        sched = RebalanceSchedule(
            policy_id=policy.id,
            enabled=True,
            schedule_json=schedule_config_to_json(cfg),
            next_run_at=next_at,
            last_run_at=None,
        )
        db.add(sched)
        db.commit()
        db.refresh(sched)
    return policy, sched


@router.post("/preview", response_model=RebalancePreviewResponse)
def rebalance_preview(
    payload: RebalancePreviewRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> RebalancePreviewResponse:
    results = preview_rebalance(db, settings, user=user, req=payload)
    return RebalancePreviewResponse(results=results)


@router.get("/schedule", response_model=RebalanceScheduleRead)
def get_rebalance_schedule(
    group_id: Annotated[int, Query(ge=1)],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RebalanceScheduleRead:
    group = _get_group_or_404(db, group_id)
    if group.owner_id is not None and group.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    if group.kind != "PORTFOLIO":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rebalance schedules are supported only for PORTFOLIO groups.",
        )

    _policy, sched = _ensure_policy_and_schedule(db, user_id=user.id, group_id=group.id)
    cfg = normalize_schedule_config(_json_load(sched.schedule_json))

    # Keep next_run_at current even if the config was edited externally.
    next_at = (
        compute_next_rebalance_at(cfg=cfg, last_run_at_utc=sched.last_run_at)
        if sched.enabled
        else None
    )
    if next_at != sched.next_run_at:
        sched.next_run_at = next_at
        db.add(sched)
        db.commit()
        db.refresh(sched)

    cfg_model = RebalanceScheduleConfig(
        frequency=cfg.frequency,
        time_local=cfg.time_local,
        timezone=cfg.timezone,
        weekday=cfg.weekday,
        day_of_month=cfg.day_of_month,
        interval_days=cfg.interval_days,
        roll_to_trading_day=cfg.roll_to_trading_day,
    )
    return RebalanceScheduleRead(
        group_id=group.id,
        enabled=bool(sched.enabled),
        config=cfg_model,
        next_run_at=sched.next_run_at,
        last_run_at=sched.last_run_at,
        updated_at=sched.updated_at,
    )


@router.put("/schedule", response_model=RebalanceScheduleRead)
def update_rebalance_schedule(
    group_id: Annotated[int, Query(ge=1)],
    payload: RebalanceScheduleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RebalanceScheduleRead:
    group = _get_group_or_404(db, group_id)
    if group.owner_id is not None and group.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    if group.kind != "PORTFOLIO":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rebalance schedules are supported only for PORTFOLIO groups.",
        )

    _policy, sched = _ensure_policy_and_schedule(db, user_id=user.id, group_id=group.id)

    if payload.enabled is not None:
        sched.enabled = bool(payload.enabled)

    if payload.config is not None:
        cfg = normalize_schedule_config(
            {
                "frequency": payload.config.frequency,
                "time_local": payload.config.time_local,
                "timezone": payload.config.timezone,
                "weekday": payload.config.weekday,
                "day_of_month": payload.config.day_of_month,
                "interval_days": payload.config.interval_days,
                "roll_to_trading_day": payload.config.roll_to_trading_day,
            }
        )
        sched.schedule_json = schedule_config_to_json(cfg)
    else:
        cfg = normalize_schedule_config(_json_load(sched.schedule_json))

    sched.next_run_at = (
        compute_next_rebalance_at(cfg=cfg, last_run_at_utc=sched.last_run_at)
        if sched.enabled
        else None
    )
    db.add(sched)
    db.commit()
    db.refresh(sched)

    cfg_model = payload.config or RebalanceScheduleConfig(
        frequency=cfg.frequency,
        time_local=cfg.time_local,
        timezone=cfg.timezone,
        weekday=cfg.weekday,
        day_of_month=cfg.day_of_month,
        interval_days=cfg.interval_days,
        roll_to_trading_day=cfg.roll_to_trading_day,
    )
    return RebalanceScheduleRead(
        group_id=group.id,
        enabled=bool(sched.enabled),
        config=cfg_model,
        next_run_at=sched.next_run_at,
        last_run_at=sched.last_run_at,
        updated_at=sched.updated_at,
    )


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
                rebalance_method=payload.rebalance_method,
                rotation=payload.rotation,
                risk=payload.risk,
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
                    portfolio_group_id=None,
                    symbol=trade.symbol,
                    exchange=trade.exchange,
                    side=trade.side,
                    qty=float(trade.qty),
                    price=(
                        round_price_to_tick(float(trade.estimated_price))
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
            rebalance_method=payload.rebalance_method,
            rotation=payload.rotation,
            risk=payload.risk,
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

        rebalance_group = db.get(Group, int(payload.group_id or 0))
        portfolio_group_id = (
            int(rebalance_group.id)
            if (
                rebalance_group is not None
                and rebalance_group.kind == "PORTFOLIO"
                and (
                    rebalance_group.owner_id is None
                    or rebalance_group.owner_id == user.id
                )
            )
            else None
        )

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
                    portfolio_group_id=portfolio_group_id,
                    symbol=trade.symbol,
                    exchange=trade.exchange,
                    side=trade.side,
                    qty=float(trade.qty),
                    price=(
                        round_price_to_tick(float(trade.estimated_price))
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

        # Best-effort: bump schedule last/next for portfolio group rebalances.
        try:
            schedule_group = db.get(Group, int(payload.group_id or 0))
            if (
                schedule_group is not None
                and schedule_group.kind == "PORTFOLIO"
                and (
                    schedule_group.owner_id is None
                    or schedule_group.owner_id == user.id
                )
                and payload.target_kind == "GROUP"
            ):
                _policy, sched = _ensure_policy_and_schedule(
                    db, user_id=user.id, group_id=schedule_group.id
                )
                cfg = normalize_schedule_config(_json_load(sched.schedule_json))
                sched.last_run_at = run.executed_at or _now_utc()
                sched.next_run_at = (
                    compute_next_rebalance_at(
                        cfg=cfg, last_run_at_utc=sched.last_run_at
                    )
                    if sched.enabled
                    else None
                )
                db.add(sched)
                db.commit()
        except Exception:
            pass

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
