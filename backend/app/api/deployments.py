from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.api.auth import get_current_user
from app.db.session import get_db
from app.models import StrategyDeployment, StrategyDeploymentState, User
from app.schemas.deployments import (
    DeploymentKind,
    DeploymentUniverse,
    PortfolioStrategyDeploymentConfigIn,
    StrategyDeploymentConfigIn,
    StrategyDeploymentCreate,
    StrategyDeploymentRead,
    StrategyDeploymentUpdate,
)
from app.services.alert_expression_dsl import parse_expression

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


def _json_dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


def _validate_universe(kind: DeploymentKind, universe: DeploymentUniverse) -> None:
    if universe.target_kind == "SYMBOL":
        if len(universe.symbols) != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="SYMBOL deployments require exactly one universe.symbols entry.",
            )
        if universe.group_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="SYMBOL deployments cannot set universe.group_id.",
            )
        if kind != "STRATEGY":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="universe.target_kind=SYMBOL requires kind=STRATEGY.",
            )
        return

    if universe.target_kind == "GROUP":
        if universe.group_id is None and not universe.symbols:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "GROUP deployments require universe.group_id or universe.symbols."
                ),
            )
        if kind != "PORTFOLIO_STRATEGY":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="universe.target_kind=GROUP requires kind=PORTFOLIO_STRATEGY.",
            )
        return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="universe.target_kind must be SYMBOL or GROUP.",
    )


def _validate_dsl(entry_dsl: str, exit_dsl: str) -> None:
    try:
        parse_expression(entry_dsl)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid entry_dsl: {exc}",
        ) from exc
    try:
        parse_expression(exit_dsl)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid exit_dsl: {exc}",
        ) from exc


def _parse_config(
    kind: DeploymentKind, cfg: dict
) -> Tuple[dict, str, str, str, str, str]:
    if kind == "STRATEGY":
        parsed = StrategyDeploymentConfigIn.parse_obj(cfg)
    else:
        parsed = PortfolioStrategyDeploymentConfigIn.parse_obj(cfg)

    daily = None
    if parsed.timeframe == "1d":
        if parsed.daily_via_intraday is not None:
            daily = parsed.daily_via_intraday.normalize().dict()
    else:
        if parsed.daily_via_intraday is not None and parsed.daily_via_intraday.enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="daily_via_intraday is only supported when timeframe is 1d.",
            )

    entry_dsl = (parsed.entry_dsl or "").strip()
    exit_dsl = (parsed.exit_dsl or "").strip()
    if not entry_dsl or not exit_dsl:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="entry_dsl and exit_dsl are required.",
        )
    _validate_dsl(entry_dsl, exit_dsl)

    normalized = parsed.dict()
    normalized["entry_dsl"] = entry_dsl
    normalized["exit_dsl"] = exit_dsl
    normalized["daily_via_intraday"] = daily
    normalized["timeframe"] = parsed.timeframe
    normalized["product"] = parsed.product
    normalized["broker_name"] = parsed.broker_name
    normalized["execution_target"] = parsed.execution_target
    normalized["direction"] = parsed.direction

    return (
        normalized,
        parsed.timeframe,
        parsed.broker_name,
        parsed.product,
        parsed.execution_target,
        parsed.direction,
    )


def _get_owned_deployment(
    db: Session, *, deployment_id: int, user: User
) -> StrategyDeployment:
    dep = (
        db.query(StrategyDeployment)
        .options(joinedload(StrategyDeployment.state))
        .filter(StrategyDeployment.id == deployment_id)
        .one_or_none()
    )
    if dep is None or dep.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found.",
        )
    return dep


@router.get("/", response_model=List[StrategyDeploymentRead])
def list_deployments(
    kind: Optional[DeploymentKind] = Query(default=None),
    enabled: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[StrategyDeploymentRead]:
    q = (
        db.query(StrategyDeployment)
        .options(joinedload(StrategyDeployment.state))
        .filter(StrategyDeployment.owner_id == user.id)
        .order_by(StrategyDeployment.id.desc())
    )
    if kind is not None:
        q = q.filter(StrategyDeployment.kind == kind)
    if enabled is not None:
        q = q.filter(StrategyDeployment.enabled.is_(enabled))
    deps = q.all()
    return [StrategyDeploymentRead.from_model(d) for d in deps]


@router.post(
    "/",
    response_model=StrategyDeploymentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_deployment(
    payload: StrategyDeploymentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StrategyDeploymentRead:
    existing = (
        db.query(StrategyDeployment)
        .filter(StrategyDeployment.owner_id == user.id)
        .filter(StrategyDeployment.name == payload.name)
        .one_or_none()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deployment with this name already exists.",
        )

    _validate_universe(payload.kind, payload.universe)
    normalized_cfg, tf, broker_name, product, exec_target, _direction = _parse_config(
        payload.kind, payload.config
    )

    exchange = None
    symbol = None
    group_id = None
    if payload.universe.target_kind == "SYMBOL":
        sym = payload.universe.symbols[0]
        exchange = sym.exchange
        symbol = sym.symbol
    else:
        group_id = payload.universe.group_id

    config_json = _json_dump(
        {
            "kind": payload.kind,
            "universe": payload.universe.dict(),
            "config": normalized_cfg,
        }
    )

    dep = StrategyDeployment(
        owner_id=user.id,
        name=payload.name.strip(),
        description=(payload.description or None),
        kind=payload.kind,
        enabled=bool(payload.enabled),
        broker_name=broker_name,
        product=product,
        execution_target=exec_target,
        target_kind=payload.universe.target_kind,
        group_id=group_id,
        exchange=exchange,
        symbol=symbol,
        timeframe=tf,
        config_json=config_json,
    )
    db.add(dep)
    db.flush()

    now = datetime.now(UTC)
    state = StrategyDeploymentState(
        deployment_id=dep.id,
        status="RUNNING" if dep.enabled else "STOPPED",
        started_at=(now if dep.enabled else None),
        stopped_at=(None if dep.enabled else now),
        state_json=None,
        last_error=None,
        last_evaluated_at=None,
        next_evaluate_at=None,
    )
    db.add(state)
    db.commit()

    db.refresh(dep)
    dep = _get_owned_deployment(db, deployment_id=dep.id, user=user)
    return StrategyDeploymentRead.from_model(dep)


@router.get("/{deployment_id}", response_model=StrategyDeploymentRead)
def get_deployment(
    deployment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StrategyDeploymentRead:
    dep = _get_owned_deployment(db, deployment_id=deployment_id, user=user)
    return StrategyDeploymentRead.from_model(dep)


@router.put("/{deployment_id}", response_model=StrategyDeploymentRead)
def update_deployment(
    deployment_id: int,
    payload: StrategyDeploymentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StrategyDeploymentRead:
    dep = _get_owned_deployment(db, deployment_id=deployment_id, user=user)

    update_data = payload.dict(exclude_unset=True)

    universe = dep_universe = None
    config = None
    kind: DeploymentKind = dep.kind  # type: ignore[assignment]
    if "universe" in update_data:
        universe = update_data.pop("universe")
    if "config" in update_data:
        config = update_data.pop("config")

    if universe is not None or config is not None:
        try:
            payload_obj = json.loads(dep.config_json or "{}")
        except Exception:
            payload_obj = {}
        dep_universe = DeploymentUniverse.parse_obj(payload_obj.get("universe") or {})
        dep_config = payload_obj.get("config") or {}

        new_universe = universe if universe is not None else dep_universe
        new_config = config if config is not None else dep_config

        _validate_universe(kind, new_universe)
        normalized_cfg, tf, broker_name, product, exec_target, _direction = (
            _parse_config(kind, new_config)
        )

        exchange = dep.exchange
        symbol = dep.symbol
        group_id = dep.group_id
        if new_universe.target_kind == "SYMBOL":
            sym = new_universe.symbols[0]
            exchange = sym.exchange
            symbol = sym.symbol
            group_id = None
        else:
            exchange = None
            symbol = None
            group_id = new_universe.group_id

        dep.target_kind = new_universe.target_kind
        dep.group_id = group_id
        dep.exchange = exchange
        dep.symbol = symbol
        dep.timeframe = tf
        dep.broker_name = broker_name
        dep.product = product
        dep.execution_target = exec_target
        dep.config_json = _json_dump(
            {
                "kind": kind,
                "universe": new_universe.dict(),
                "config": normalized_cfg,
            }
        )

        if dep.state is not None:
            now = datetime.now(UTC)
            dep.state.status = "STOPPED"
            dep.state.stopped_at = now
            dep.state.started_at = None
            dep.state.last_error = None
            dep.state.state_json = None
            dep.state.last_evaluated_at = None
            dep.state.next_evaluate_at = None

    if "name" in update_data:
        dep.name = (update_data["name"] or "").strip()
    if "description" in update_data:
        dep.description = update_data["description"] or None
    if "enabled" in update_data:
        dep.enabled = bool(update_data["enabled"])
        if dep.state is not None:
            now = datetime.now(UTC)
            if dep.enabled:
                dep.state.status = "RUNNING"
                dep.state.started_at = dep.state.started_at or now
                dep.state.stopped_at = None
            else:
                dep.state.status = "STOPPED"
                dep.state.stopped_at = now

    db.add(dep)
    db.commit()
    dep = _get_owned_deployment(db, deployment_id=deployment_id, user=user)
    return StrategyDeploymentRead.from_model(dep)


@router.post("/{deployment_id}/start", response_model=StrategyDeploymentRead)
def start_deployment(
    deployment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StrategyDeploymentRead:
    dep = _get_owned_deployment(db, deployment_id=deployment_id, user=user)
    dep.enabled = True
    if dep.state is None:
        dep.state = StrategyDeploymentState(deployment_id=dep.id, status="RUNNING")
    now = datetime.now(UTC)
    dep.state.status = "RUNNING"
    dep.state.started_at = dep.state.started_at or now
    dep.state.stopped_at = None
    dep.state.last_error = None
    db.add(dep)
    db.commit()
    dep = _get_owned_deployment(db, deployment_id=deployment_id, user=user)
    return StrategyDeploymentRead.from_model(dep)


@router.post("/{deployment_id}/stop", response_model=StrategyDeploymentRead)
def stop_deployment(
    deployment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StrategyDeploymentRead:
    dep = _get_owned_deployment(db, deployment_id=deployment_id, user=user)
    dep.enabled = False
    if dep.state is None:
        dep.state = StrategyDeploymentState(deployment_id=dep.id, status="STOPPED")
    now = datetime.now(UTC)
    dep.state.status = "STOPPED"
    dep.state.stopped_at = now
    db.add(dep)
    db.commit()
    dep = _get_owned_deployment(db, deployment_id=deployment_id, user=user)
    return StrategyDeploymentRead.from_model(dep)


@router.delete(
    "/{deployment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_deployment(
    deployment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    dep = _get_owned_deployment(db, deployment_id=deployment_id, user=user)
    db.delete(dep)
    db.commit()


__all__ = ["router"]
