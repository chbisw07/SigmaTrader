from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import SignalStrategy, SignalStrategyVersion, User
from app.schemas.alerts_v3 import AlertVariableDef
from app.schemas.signal_strategies import (
    SignalStrategyCreate,
    SignalStrategyExport,
    SignalStrategyImportRequest,
    SignalStrategyInputDef,
    SignalStrategyOutputDef,
    SignalStrategyRead,
    SignalStrategyUpdate,
    SignalStrategyVersionCreate,
    SignalStrategyVersionRead,
)
from app.services.alerts_v3_expression import IndicatorAlertError
from app.services.signal_strategies import (
    dump_inputs,
    dump_outputs,
    dump_regimes,
    dump_tags,
    dump_variables,
    load_inputs,
    load_outputs,
    load_regimes,
    load_tags,
    load_variables,
    strategy_usage_counts,
    validate_strategy_version,
)

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


def _read_strategy(
    db: Session,
    *,
    s: SignalStrategy,
    include_latest: bool,
    include_usage: bool,
) -> SignalStrategyRead:
    tags = load_tags(getattr(s, "tags_json", "[]") or "[]")
    regimes = load_regimes(getattr(s, "regimes_json", "[]") or "[]")

    latest: SignalStrategyVersionRead | None = None
    used_by_alerts = 0
    used_by_screeners = 0

    versions: list[SignalStrategyVersion] = []
    if include_latest or include_usage:
        versions = (
            db.query(SignalStrategyVersion)
            .filter(SignalStrategyVersion.strategy_id == s.id)
            .order_by(SignalStrategyVersion.version.desc())
            .all()
        )

    if include_usage and versions:
        version_ids = [v.id for v in versions]
        alerts_map, screeners_map = strategy_usage_counts(db, version_ids=version_ids)
        used_by_alerts = sum(alerts_map.get(v.id, 0) for v in versions)
        used_by_screeners = sum(screeners_map.get(v.id, 0) for v in versions)

    if include_latest and versions:
        v = versions[0]
        latest = _read_version(v)

    return SignalStrategyRead(
        id=s.id,
        scope=(s.scope or "USER"),
        owner_id=s.owner_id,
        name=s.name,
        description=s.description,
        tags=tags,
        regimes=regimes,  # type: ignore[arg-type]
        latest_version=int(getattr(s, "latest_version", 1) or 1),
        created_at=s.created_at,
        updated_at=s.updated_at,
        latest=latest,
        used_by_alerts=used_by_alerts,
        used_by_screeners=used_by_screeners,
    )


def _read_version(v: SignalStrategyVersion) -> SignalStrategyVersionRead:
    inputs = load_inputs(getattr(v, "inputs_json", "[]") or "[]")
    variables = load_variables(getattr(v, "variables_json", "[]") or "[]")
    outputs = load_outputs(getattr(v, "outputs_json", "[]") or "[]")
    compat = {}
    raw_compat = getattr(v, "compatibility_json", "") or "{}"
    try:
        parsed = json.loads(raw_compat)
        if isinstance(parsed, dict):
            compat = parsed
    except json.JSONDecodeError:
        compat = {}

    return SignalStrategyVersionRead(
        id=v.id,
        strategy_id=v.strategy_id,
        version=v.version,
        inputs=inputs,
        variables=variables,
        outputs=outputs,
        compatibility=compat,
        enabled=bool(getattr(v, "enabled", True)),
        created_at=v.created_at,
    )


def _get_strategy_or_404(
    db: Session, *, user_id: int, strategy_id: int
) -> SignalStrategy:
    s = db.get(SignalStrategy, strategy_id)
    if s is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if s.scope == "USER" and s.owner_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return s


def _get_version_or_404(
    db: Session, *, user_id: int, version_id: int
) -> SignalStrategyVersion:
    v = db.get(SignalStrategyVersion, version_id)
    if v is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    s = db.get(SignalStrategy, v.strategy_id)
    if s is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if s.scope == "USER" and s.owner_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return v


@router.get("/", response_model=List[SignalStrategyRead])
def list_signal_strategies(
    include_latest: bool = Query(True),
    include_usage: bool = Query(True),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[SignalStrategyRead]:
    rows = (
        db.query(SignalStrategy)
        .filter((SignalStrategy.scope != "USER") | (SignalStrategy.owner_id == user.id))
        .order_by(SignalStrategy.updated_at.desc())
        .all()
    )
    return [
        _read_strategy(
            db,
            s=s,
            include_latest=include_latest,
            include_usage=include_usage,
        )
        for s in rows
    ]


@router.get("/{strategy_id}", response_model=SignalStrategyRead)
def get_signal_strategy(
    strategy_id: int,
    include_versions: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SignalStrategyRead:
    s = _get_strategy_or_404(db, user_id=user.id, strategy_id=strategy_id)
    out = _read_strategy(db, s=s, include_latest=True, include_usage=True)
    if include_versions:
        # Versions are available via the /versions endpoint.
        pass
    return out


@router.get("/{strategy_id}/versions", response_model=List[SignalStrategyVersionRead])
def list_signal_strategy_versions(
    strategy_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[SignalStrategyVersionRead]:
    s = _get_strategy_or_404(db, user_id=user.id, strategy_id=strategy_id)
    versions = (
        db.query(SignalStrategyVersion)
        .filter(SignalStrategyVersion.strategy_id == s.id)
        .order_by(SignalStrategyVersion.version.desc())
        .all()
    )
    return [_read_version(v) for v in versions]


@router.post(
    "/",
    response_model=SignalStrategyRead,
    status_code=status.HTTP_201_CREATED,
)
def create_signal_strategy(
    payload: SignalStrategyCreate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> SignalStrategyRead:
    scope = (payload.scope or "USER").strip().upper()
    owner_id = user.id if scope == "USER" else None

    existing = (
        db.query(SignalStrategy)
        .filter(SignalStrategy.scope == scope, SignalStrategy.owner_id == owner_id)
        .filter(SignalStrategy.name == payload.name)
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Strategy with this name already exists.",
        )

    try:
        compatibility, _compiled = validate_strategy_version(
            db,
            user_id=user.id,
            inputs=payload.version.inputs,
            variables=payload.version.variables,
            outputs=payload.version.outputs,
            dsl_profile=settings.dsl_profile,
        )
    except IndicatorAlertError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    now = datetime.now(UTC)
    s = SignalStrategy(
        scope=scope,
        owner_id=owner_id,
        name=payload.name,
        description=payload.description,
        tags_json=dump_tags(payload.tags),
        regimes_json=dump_regimes([str(r) for r in payload.regimes]),
        latest_version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(s)
    db.flush()

    v = SignalStrategyVersion(
        strategy_id=s.id,
        version=1,
        inputs_json=dump_inputs(payload.version.inputs),
        variables_json=dump_variables(payload.version.variables),
        outputs_json=dump_outputs(payload.version.outputs),
        compatibility_json=json.dumps(compatibility, default=str),
        enabled=payload.version.enabled,
        created_at=now,
    )
    db.add(v)
    db.commit()
    db.refresh(s)
    return _read_strategy(db, s=s, include_latest=True, include_usage=True)


@router.post(
    "/{strategy_id}/versions",
    response_model=SignalStrategyVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_signal_strategy_version(
    strategy_id: int,
    payload: SignalStrategyVersionCreate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> SignalStrategyVersionRead:
    s = _get_strategy_or_404(db, user_id=user.id, strategy_id=strategy_id)
    if s.scope == "GLOBAL" and s.owner_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid strategy scope."
        )

    next_version = int(getattr(s, "latest_version", 1) or 1) + 1

    try:
        compatibility, _compiled = validate_strategy_version(
            db,
            user_id=user.id,
            inputs=payload.inputs,
            variables=payload.variables,
            outputs=payload.outputs,
            dsl_profile=settings.dsl_profile,
        )
    except IndicatorAlertError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    now = datetime.now(UTC)
    v = SignalStrategyVersion(
        strategy_id=s.id,
        version=next_version,
        inputs_json=dump_inputs(payload.inputs),
        variables_json=dump_variables(payload.variables),
        outputs_json=dump_outputs(payload.outputs),
        compatibility_json=json.dumps(compatibility, default=str),
        enabled=payload.enabled,
        created_at=now,
    )
    db.add(v)
    s.latest_version = next_version
    s.updated_at = now
    db.add(s)
    db.commit()
    db.refresh(v)
    return _read_version(v)


@router.put("/{strategy_id}", response_model=SignalStrategyRead)
def update_signal_strategy(
    strategy_id: int,
    payload: SignalStrategyUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SignalStrategyRead:
    s = _get_strategy_or_404(db, user_id=user.id, strategy_id=strategy_id)

    if payload.name is not None and payload.name != s.name:
        scope = (payload.scope or s.scope or "USER").strip().upper()
        owner_id = s.owner_id if scope == "USER" else None
        existing = (
            db.query(SignalStrategy)
            .filter(SignalStrategy.scope == scope, SignalStrategy.owner_id == owner_id)
            .filter(SignalStrategy.name == payload.name)
            .first()
        )
        if existing is not None and existing.id != s.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Strategy with this name already exists.",
            )
        s.name = payload.name

    if payload.description is not None:
        s.description = payload.description
    if payload.tags is not None:
        s.tags_json = dump_tags(payload.tags)
    if payload.regimes is not None:
        s.regimes_json = dump_regimes([str(r) for r in payload.regimes])
    if payload.scope is not None:
        s.scope = payload.scope
        if (payload.scope or "").upper() == "GLOBAL":
            s.owner_id = None

    s.updated_at = datetime.now(UTC)
    db.add(s)
    db.commit()
    db.refresh(s)
    return _read_strategy(db, s=s, include_latest=True, include_usage=True)


@router.delete(
    "/{strategy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def delete_signal_strategy(
    strategy_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    s = _get_strategy_or_404(db, user_id=user.id, strategy_id=strategy_id)
    versions = (
        db.query(SignalStrategyVersion.id)
        .filter(SignalStrategyVersion.strategy_id == s.id)
        .all()
    )
    version_ids = [int(v[0]) for v in versions]
    alerts_map, screeners_map = strategy_usage_counts(db, version_ids=version_ids)
    if sum(alerts_map.values()) + sum(screeners_map.values()) > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Strategy is in use and cannot be deleted.",
        )
    db.delete(s)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{strategy_id}/export", response_model=SignalStrategyExport)
def export_signal_strategy(
    strategy_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SignalStrategyExport:
    s = _get_strategy_or_404(db, user_id=user.id, strategy_id=strategy_id)
    tags = load_tags(s.tags_json or "[]")
    regimes = load_regimes(s.regimes_json or "[]")
    versions = (
        db.query(SignalStrategyVersion)
        .filter(SignalStrategyVersion.strategy_id == s.id)
        .order_by(SignalStrategyVersion.version.asc())
        .all()
    )
    items: List[Dict[str, Any]] = []
    for v in versions:
        items.append(
            {
                "version": v.version,
                "inputs": json.loads(v.inputs_json or "[]"),
                "variables": json.loads(v.variables_json or "[]"),
                "outputs": json.loads(v.outputs_json or "[]"),
                "compatibility": json.loads(v.compatibility_json or "{}"),
                "enabled": bool(getattr(v, "enabled", True)),
            }
        )
    return SignalStrategyExport(
        name=s.name,
        description=s.description,
        tags=tags,
        regimes=regimes,
        scope=s.scope,
        versions=items,
    )


@router.post(
    "/import",
    response_model=SignalStrategyRead,
    status_code=status.HTTP_201_CREATED,
)
def import_signal_strategy(
    payload: SignalStrategyImportRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> SignalStrategyRead:
    data = payload.payload or {}
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid import payload."
        )

    name = str(data.get("name") or "").strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Import payload missing name.",
        )

    scope = str(data.get("scope") or "USER").strip().upper()
    if scope not in {"USER", "GLOBAL"}:
        scope = "USER"
    owner_id = user.id if scope == "USER" else None

    existing = (
        db.query(SignalStrategy)
        .filter(SignalStrategy.scope == scope, SignalStrategy.owner_id == owner_id)
        .filter(SignalStrategy.name == name)
        .first()
    )
    if existing is not None:
        if not payload.replace_existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Strategy with this name already exists.",
            )
        # Safe replace only when not used.
        versions = (
            db.query(SignalStrategyVersion.id)
            .filter(SignalStrategyVersion.strategy_id == existing.id)
            .all()
        )
        version_ids = [int(v[0]) for v in versions]
        alerts_map, screeners_map = strategy_usage_counts(db, version_ids=version_ids)
        if sum(alerts_map.values()) + sum(screeners_map.values()) > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Existing strategy is in use; cannot replace.",
            )
        db.delete(existing)
        db.flush()

    versions_in = data.get("versions") or []
    if not isinstance(versions_in, list) or not versions_in:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Import payload missing versions.",
        )

    tags = data.get("tags") or []
    regimes = data.get("regimes") or []
    description = data.get("description")

    now = datetime.now(UTC)
    s = SignalStrategy(
        scope=scope,
        owner_id=owner_id,
        name=name,
        description=description if isinstance(description, str) else None,
        tags_json=dump_tags(tags if isinstance(tags, list) else []),
        regimes_json=dump_regimes(regimes if isinstance(regimes, list) else []),
        latest_version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(s)
    db.flush()

    latest = 0
    for item in versions_in:
        if not isinstance(item, dict):
            continue
        ver = int(item.get("version") or 0)
        inputs = item.get("inputs") or []
        variables = item.get("variables") or []
        outputs = item.get("outputs") or []
        enabled = bool(item.get("enabled", True))
        try:
            v_create = SignalStrategyVersionCreate(
                inputs=[
                    SignalStrategyInputDef(**i) for i in inputs if isinstance(i, dict)
                ],
                variables=[
                    AlertVariableDef(**v) for v in variables if isinstance(v, dict)
                ],
                outputs=[
                    SignalStrategyOutputDef(**o) for o in outputs if isinstance(o, dict)
                ],
                enabled=enabled,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid version payload: {exc}",
            ) from exc

        try:
            compatibility, _compiled = validate_strategy_version(
                db,
                user_id=user.id,
                inputs=v_create.inputs,
                variables=v_create.variables,
                outputs=v_create.outputs,
                dsl_profile=settings.dsl_profile,
            )
        except IndicatorAlertError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid DSL in imported strategy: {exc}",
            ) from exc

        v = SignalStrategyVersion(
            strategy_id=s.id,
            version=ver if ver > 0 else (latest + 1),
            inputs_json=json.dumps(inputs, default=str),
            variables_json=json.dumps(variables, default=str),
            outputs_json=json.dumps(outputs, default=str),
            compatibility_json=json.dumps(compatibility, default=str),
            enabled=enabled,
            created_at=now,
        )
        db.add(v)
        latest = max(latest, v.version)

    if latest <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid versions found in import payload.",
        )
    s.latest_version = latest
    db.add(s)
    db.commit()
    db.refresh(s)
    return _read_strategy(db, s=s, include_latest=True, include_usage=True)


@router.get("/versions/{version_id}", response_model=SignalStrategyVersionRead)
def get_signal_strategy_version(
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SignalStrategyVersionRead:
    v = _get_version_or_404(db, user_id=user.id, version_id=version_id)
    return _read_version(v)


__all__ = ["router"]
