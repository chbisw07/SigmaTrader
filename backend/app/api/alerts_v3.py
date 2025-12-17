from __future__ import annotations

import json
from typing import Any, Iterable, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import (
    AlertDefinition,
    AlertEvent,
    CustomIndicator,
    Group,
    GroupMember,
    User,
)
from app.schemas.alerts_v3 import (
    AlertDefinitionCreate,
    AlertDefinitionRead,
    AlertDefinitionUpdate,
    AlertEventRead,
    AlertTradeTemplate,
    AlertV3TestRequest,
    AlertV3TestResponse,
    AlertV3TestResult,
    AlertVariableDef,
    CustomIndicatorCreate,
    CustomIndicatorRead,
    CustomIndicatorUpdate,
)
from app.schemas.positions import HoldingRead
from app.services.alerts_v3_compiler import (
    compile_alert_definition,
    compile_alert_expression,
    compile_custom_indicators_for_user,
)
from app.services.alerts_v3_expression import (
    BinaryNode,
    CallNode,
    ComparisonNode,
    EventNode,
    ExprNode,
    IdentNode,
    LogicalNode,
    NotNode,
    UnaryNode,
    eval_condition,
)
from app.services.indicator_alerts import IndicatorAlertError

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


def _model_validate(schema_cls, obj):
    """Compat helper for Pydantic v1/v2."""

    if hasattr(schema_cls, "model_validate"):
        return schema_cls.model_validate(obj)  # type: ignore[attr-defined]
    return schema_cls.from_orm(obj)  # type: ignore[call-arg]


def _schema_validate(schema_cls, obj):
    """Compat helper for validating dict payloads with Pydantic v1/v2."""

    if hasattr(schema_cls, "model_validate"):
        return schema_cls.model_validate(obj)  # type: ignore[attr-defined]
    return schema_cls.parse_obj(obj)  # type: ignore[call-arg]


def _variables_to_json(variables: list[Any]) -> str:
    payload = []
    for v in variables:
        if hasattr(v, "model_dump"):
            payload.append(v.model_dump())  # type: ignore[attr-defined]
        else:
            payload.append(v.dict())  # type: ignore[attr-defined]
    return json.dumps(payload, default=str)


def _variables_from_json(raw: str) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        return []
    out: list[dict[str, Any]] = []
    for item in parsed:
        if isinstance(item, dict):
            out.append(item)
    return out


def _action_params_from_json(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _action_params_to_json(
    action_type: str | None,
    params: dict[str, Any] | None,
) -> tuple[str, str]:
    action = (action_type or "ALERT_ONLY").strip().upper()
    if action not in {"ALERT_ONLY", "BUY", "SELL"}:
        action = "ALERT_ONLY"

    if action == "ALERT_ONLY":
        return action, "{}"

    template = _schema_validate(AlertTradeTemplate, params or {})
    dumped = (
        template.model_dump() if hasattr(template, "model_dump") else template.dict()
    )
    return action, json.dumps(dumped, default=str)


def _alert_to_read(alert: AlertDefinition) -> AlertDefinitionRead:
    vars_raw = _variables_from_json(alert.variables_json or "[]")
    variables = [AlertVariableDef(**v) for v in vars_raw if isinstance(v, dict)]
    action_type, action_params_json = _action_params_to_json(
        getattr(alert, "action_type", None),
        _action_params_from_json(getattr(alert, "action_params_json", "") or "{}"),
    )
    action_params = _action_params_from_json(action_params_json)
    return AlertDefinitionRead(
        id=alert.id,
        name=alert.name,
        target_kind=alert.target_kind,
        target_ref=alert.target_ref,
        exchange=alert.exchange,
        action_type=action_type,
        action_params=action_params,
        evaluation_cadence=alert.evaluation_cadence,
        variables=variables,
        condition_dsl=alert.condition_dsl,
        trigger_mode=alert.trigger_mode,
        throttle_seconds=alert.throttle_seconds,
        only_market_hours=alert.only_market_hours,
        expires_at=alert.expires_at,
        enabled=alert.enabled,
        last_evaluated_at=alert.last_evaluated_at,
        last_triggered_at=alert.last_triggered_at,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
    )


def _custom_params_from_json(raw: str) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    out: list[str] = []
    for p in parsed:
        if isinstance(p, str):
            out.append(p)
        elif isinstance(p, dict) and isinstance(p.get("name"), str):
            out.append(p["name"])
    return out


def _custom_to_read(ind: CustomIndicator) -> CustomIndicatorRead:
    data = _model_validate(CustomIndicatorRead, ind)
    data.params = _custom_params_from_json(ind.params_json)  # type: ignore[assignment]
    return data


def _variables_to_dicts(variables: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for v in variables:
        if hasattr(v, "model_dump"):
            dumped = v.model_dump()  # type: ignore[attr-defined]
        else:
            dumped = v.dict()  # type: ignore[attr-defined]
        if isinstance(dumped, dict):
            out.append(dumped)
    return out


def _iter_target_symbols(
    db: Session,
    settings: Settings,
    *,
    user: User,
    target_kind: str,
    target_ref: str,
    exchange: str,
) -> Iterable[Tuple[str, str]]:
    kind = (target_kind or "").upper()
    ref = (target_ref or "").strip()
    exch = (exchange or "NSE").upper()

    if kind == "SYMBOL":
        if not ref:
            return
        yield ref.upper(), exch
        return

    if kind == "GROUP":
        try:
            group_id = int(ref)
        except ValueError:
            return
        group = db.get(Group, group_id)
        if group is None:
            return
        if group.owner_id is not None and group.owner_id != user.id:
            return
        members = (
            db.query(GroupMember)
            .filter(GroupMember.group_id == group_id)
            .order_by(GroupMember.created_at)
            .all()
        )
        for m in members:
            yield m.symbol.upper(), (m.exchange or "NSE").upper()
        return

    if kind == "HOLDINGS":
        # Resolve live holdings for the user.
        try:
            from app.api.positions import list_holdings

            holdings = list_holdings(db=db, settings=settings, user=user)
        except Exception:
            return
        for h in holdings:
            yield h.symbol.upper(), ((getattr(h, "exchange", None) or "NSE").upper())


_HOLDINGS_SNAPSHOT_METRICS = {
    "TODAY_PNL_PCT",
    "PNL_PCT",
    "CURRENT_VALUE",
    "INVESTED",
    "QTY",
    "AVG_PRICE",
}


def _iter_expr_nodes(expr: ExprNode) -> Iterable[ExprNode]:
    yield expr
    if isinstance(expr, IdentNode):
        return
    if isinstance(expr, CallNode):
        for a in expr.args:
            yield from _iter_expr_nodes(a)
        return
    if isinstance(expr, UnaryNode):
        yield from _iter_expr_nodes(expr.child)
        return
    if isinstance(expr, BinaryNode):
        yield from _iter_expr_nodes(expr.left)
        yield from _iter_expr_nodes(expr.right)
        return
    if isinstance(expr, (ComparisonNode, EventNode)):
        yield from _iter_expr_nodes(expr.left)
        yield from _iter_expr_nodes(expr.right)
        return
    if isinstance(expr, LogicalNode):
        for c in expr.children:
            yield from _iter_expr_nodes(c)
        return
    if isinstance(expr, NotNode):
        yield from _iter_expr_nodes(expr.child)


def _needs_holdings_snapshot(expr: ExprNode) -> bool:
    for n in _iter_expr_nodes(expr):
        if isinstance(n, IdentNode) and n.name.upper() in _HOLDINGS_SNAPSHOT_METRICS:
            return True
    return False


@router.get("/", response_model=List[AlertDefinitionRead])
def list_alert_definitions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[AlertDefinitionRead]:
    rows = (
        db.query(AlertDefinition)
        .filter(AlertDefinition.user_id == user.id)
        .order_by(AlertDefinition.updated_at.desc())
        .all()
    )
    return [_alert_to_read(a) for a in rows]


@router.post("/", response_model=AlertDefinitionRead)
def create_alert_definition(
    payload: AlertDefinitionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AlertDefinitionRead:
    action_type, action_params_json = _action_params_to_json(
        payload.action_type,
        payload.action_params,
    )
    alert = AlertDefinition(
        user_id=user.id,
        name=payload.name,
        target_kind=payload.target_kind,
        target_ref=payload.target_ref,
        exchange=(payload.exchange or None),
        action_type=action_type,
        action_params_json=action_params_json,
        evaluation_cadence=(payload.evaluation_cadence or "").strip(),
        variables_json=_variables_to_json(payload.variables),
        condition_dsl=payload.condition_dsl,
        trigger_mode=payload.trigger_mode,
        throttle_seconds=payload.throttle_seconds,
        only_market_hours=payload.only_market_hours,
        expires_at=payload.expires_at,
        enabled=payload.enabled,
    )
    db.add(alert)
    db.flush()

    try:
        compile_alert_definition(db, alert=alert, user_id=user.id)
    except IndicatorAlertError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    db.commit()
    db.refresh(alert)
    return _alert_to_read(alert)


def _get_alert_or_404(db: Session, user_id: int, alert_id: int) -> AlertDefinition:
    alert = db.get(AlertDefinition, alert_id)
    if alert is None or alert.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return alert


@router.put("/{alert_id}", response_model=AlertDefinitionRead)
def update_alert_definition(
    alert_id: int,
    payload: AlertDefinitionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AlertDefinitionRead:
    alert = _get_alert_or_404(db, user.id, alert_id)

    for field in (
        "name",
        "target_kind",
        "target_ref",
        "exchange",
        "action_type",
        "evaluation_cadence",
        "condition_dsl",
        "trigger_mode",
        "throttle_seconds",
        "only_market_hours",
        "expires_at",
        "enabled",
    ):
        val = getattr(payload, field)
        if val is not None:
            setattr(alert, field, val)

    if payload.variables is not None:
        alert.variables_json = _variables_to_json(payload.variables)

    if payload.action_params is not None:
        alert.action_params_json = json.dumps(payload.action_params or {}, default=str)

    # Canonicalize action fields so older payloads and partial updates keep
    # consistent defaults.
    normalized_action, normalized_params_json = _action_params_to_json(
        alert.action_type,
        _action_params_from_json(alert.action_params_json or "{}"),
    )
    alert.action_type = normalized_action
    alert.action_params_json = normalized_params_json

    try:
        compile_alert_definition(db, alert=alert, user_id=user.id)
    except IndicatorAlertError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    db.commit()
    db.refresh(alert)
    return _alert_to_read(alert)


@router.delete(
    "/{alert_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_alert_definition(
    alert_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    alert = _get_alert_or_404(db, user.id, alert_id)
    db.delete(alert)
    db.commit()


@router.get("/indicators/", response_model=List[CustomIndicatorRead])
def list_custom_indicators(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[CustomIndicatorRead]:
    rows = (
        db.query(CustomIndicator)
        .filter(CustomIndicator.user_id == user.id)
        .order_by(CustomIndicator.updated_at.desc())
        .all()
    )
    return [_custom_to_read(r) for r in rows]


@router.post("/indicators/", response_model=CustomIndicatorRead)
def create_custom_indicator(
    payload: CustomIndicatorCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CustomIndicatorRead:
    ind = CustomIndicator(
        user_id=user.id,
        name=payload.name,
        description=payload.description,
        params_json=json.dumps(payload.params, default=str),
        body_dsl=payload.body_dsl,
        enabled=payload.enabled,
    )
    db.add(ind)
    db.flush()

    try:
        compile_custom_indicators_for_user(db, user_id=user.id)
    except IndicatorAlertError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    db.commit()
    db.refresh(ind)
    return _custom_to_read(ind)


def _get_indicator_or_404(
    db: Session, user_id: int, indicator_id: int
) -> CustomIndicator:
    ind = db.get(CustomIndicator, indicator_id)
    if ind is None or ind.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return ind


@router.put("/indicators/{indicator_id}", response_model=CustomIndicatorRead)
def update_custom_indicator(
    indicator_id: int,
    payload: CustomIndicatorUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CustomIndicatorRead:
    ind = _get_indicator_or_404(db, user.id, indicator_id)

    for field in ("name", "description", "body_dsl", "enabled"):
        val = getattr(payload, field)
        if val is not None:
            setattr(ind, field, val)

    if payload.params is not None:
        ind.params_json = json.dumps(payload.params, default=str)

    # Force recompilation.
    ind.body_ast_json = None
    db.add(ind)

    try:
        compile_custom_indicators_for_user(db, user_id=user.id)
    except IndicatorAlertError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    db.commit()
    db.refresh(ind)
    return _custom_to_read(ind)


@router.delete(
    "/indicators/{indicator_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_custom_indicator(
    indicator_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    ind = _get_indicator_or_404(db, user.id, indicator_id)
    db.delete(ind)
    db.commit()


@router.get("/events/", response_model=List[AlertEventRead])
def list_alert_events(
    alert_id: Optional[int] = Query(None),
    symbol: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[AlertEventRead]:
    q = db.query(AlertEvent).filter(AlertEvent.user_id == user.id)
    if alert_id is not None:
        q = q.filter(AlertEvent.alert_definition_id == alert_id)
    if symbol:
        q = q.filter(AlertEvent.symbol == symbol)
    rows = q.order_by(AlertEvent.triggered_at.desc()).limit(limit).all()

    out: List[AlertEventRead] = []
    for e in rows:
        data = _model_validate(AlertEventRead, e)
        try:
            data.snapshot = json.loads(e.snapshot_json or "{}")  # type: ignore[assignment]
        except json.JSONDecodeError:
            data.snapshot = {}  # type: ignore[assignment]
        out.append(data)
    return out


@router.post("/test", response_model=AlertV3TestResponse)
def test_alert_expression_api(
    payload: AlertV3TestRequest,
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> AlertV3TestResponse:
    """Preview a v3 alert condition on the latest bar for each target symbol.

    This endpoint is intended for UI tooling ("Run condition on last bar")
    and returns per-symbol match status along with a debug snapshot.
    """

    try:
        custom = compile_custom_indicators_for_user(db, user_id=user.id)
        vars_dicts = _variables_to_dicts(payload.variables)
        expr_ast, cadence = compile_alert_expression(
            db,
            user_id=user.id,
            variables=vars_dicts,
            condition_dsl=payload.condition_dsl,
            evaluation_cadence=payload.evaluation_cadence,
            custom_indicators=custom,
        )
    except IndicatorAlertError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    holdings_map: dict[str, HoldingRead] | None = None
    if payload.target_kind.upper() == "HOLDINGS" or _needs_holdings_snapshot(expr_ast):
        try:
            from app.api.positions import list_holdings

            holdings = list_holdings(db=db, settings=settings, user=user)
            holdings_map = {h.symbol.upper(): h for h in holdings}
        except Exception:
            holdings_map = {}

    exch = (payload.exchange or "NSE").upper()
    results: list[AlertV3TestResult] = []
    for symbol, exchange in _iter_target_symbols(
        db,
        settings,
        user=user,
        target_kind=payload.target_kind,
        target_ref=payload.target_ref,
        exchange=exch,
    ):
        if len(results) >= limit:
            break
        try:
            holding = (
                holdings_map.get(symbol.upper()) if holdings_map is not None else None
            )
            matched, snapshot, bar_time = eval_condition(
                expr_ast,
                db=db,
                settings=settings,
                symbol=symbol,
                exchange=exchange,
                holding=holding,
                custom_indicators=custom,
            )
            results.append(
                AlertV3TestResult(
                    symbol=symbol,
                    exchange=exchange,
                    matched=matched,
                    bar_time=bar_time,
                    snapshot=snapshot,
                )
            )
        except IndicatorAlertError as exc:
            results.append(
                AlertV3TestResult(
                    symbol=symbol,
                    exchange=exchange,
                    matched=False,
                    snapshot={},
                    error=str(exc),
                )
            )
        except Exception:
            results.append(
                AlertV3TestResult(
                    symbol=symbol,
                    exchange=exchange,
                    matched=False,
                    snapshot={},
                    error="Evaluation failed.",
                )
            )

    return AlertV3TestResponse(evaluation_cadence=cadence, results=results)


__all__ = ["router"]
