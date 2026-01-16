from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import Settings, get_settings
from app.core.time_utils import to_utc_or_none
from app.db.session import get_db
from app.models import IndicatorRule, User
from app.schemas.indicator_rules import (
    IndicatorCondition,
    IndicatorRuleCreate,
    IndicatorRuleRead,
    IndicatorRuleUpdate,
    IndicatorType,
)
from app.services.alert_expression import expression_to_dict
from app.services.alert_expression_dsl import parse_expression
from app.services.indicator_alerts import (
    IndicatorAlertError,
    compute_indicator_preview,
)
from app.services.market_data import Timeframe

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


def _deserialize_conditions_json(rule: IndicatorRule) -> list[IndicatorCondition]:
    import json

    raw = rule.conditions_json or "[]"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = []
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        parsed = []
    return [IndicatorCondition.parse_obj(item) for item in parsed]


def _indicator_rule_to_read(rule: IndicatorRule) -> IndicatorRuleRead:
    """Convert an ORM IndicatorRule into a read schema."""

    import json

    conditions = _deserialize_conditions_json(rule)
    if rule.dsl_expression or rule.expression_json:
        # For DSL/AST-backed rules, conditions_json is considered an
        # implementation detail; expose an empty list to the UI and rely
        # on dsl_expression for display.
        conditions = []
    try:
        action_params = json.loads(rule.action_params_json or "{}")
    except json.JSONDecodeError:
        action_params = {}

    return IndicatorRuleRead(
        id=rule.id,
        strategy_id=rule.strategy_id,
        name=rule.name,
        symbol=rule.symbol,
        universe=rule.universe,
        exchange=rule.exchange,
        target_type=rule.target_type,
        target_id=rule.target_id,
        timeframe=rule.timeframe,
        logic=rule.logic,  # type: ignore[arg-type]
        conditions=conditions,
        dsl_expression=rule.dsl_expression,
        trigger_mode=rule.trigger_mode,  # type: ignore[arg-type]
        action_type=rule.action_type,  # type: ignore[arg-type]
        action_params=action_params,
        expires_at=rule.expires_at,
        enabled=rule.enabled,
        last_triggered_at=rule.last_triggered_at,
        last_evaluated_at=rule.last_evaluated_at,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def _ensure_owner(rule: IndicatorRule, user: User) -> None:
    if rule.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found.",
        )


class IndicatorPreview(BaseModel):
    value: Optional[float] = None
    prev_value: Optional[float] = None
    bar_time: Optional[datetime] = None


@router.get("/preview", response_model=IndicatorPreview)
def preview_indicator_value(
    symbol: str = Query(..., min_length=1),
    exchange: str = Query("NSE", min_length=1),
    timeframe: Timeframe = Query("1d"),
    indicator: IndicatorType = Query("PRICE"),
    period: int | None = Query(None, ge=1),
    window: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> IndicatorPreview:
    """Return the latest indicator value for a symbol/timeframe.

    Used by the alert configuration UI so users can see the current
    indicator level while choosing thresholds.
    """

    params: dict[str, Any] = {}
    if period is not None:
        params["period"] = period
    if window is not None:
        params["window"] = window

    sample = compute_indicator_preview(
        db,
        settings,
        symbol=symbol,
        exchange=exchange,
        timeframe=timeframe,
        indicator=indicator,
        params=params,
    )
    return IndicatorPreview(
        value=sample.value,
        prev_value=sample.prev_value,
        bar_time=sample.bar_time,
    )


@router.get("/", response_model=List[IndicatorRuleRead])
def list_indicator_rules(
    symbol: str | None = Query(None, min_length=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[IndicatorRule]:
    """Return indicator rules for the current user."""

    query = db.query(IndicatorRule).filter(IndicatorRule.user_id == user.id)
    if symbol:
        query = query.filter(IndicatorRule.symbol == symbol)
    rules: List[IndicatorRule] = query.order_by(IndicatorRule.created_at.desc()).all()
    return [_indicator_rule_to_read(r) for r in rules]


@router.post(
    "/",
    response_model=IndicatorRuleRead,
    status_code=status.HTTP_201_CREATED,
)
def create_indicator_rule(
    payload: IndicatorRuleCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IndicatorRule:
    """Create a new indicator-based alert rule for the current user."""

    import json

    from app.schemas.indicator_rules import (  # local import to avoid cycles
        IndicatorCondition,
    )

    if not payload.conditions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one condition is required.",
        )

    if payload.target_type is not None and not payload.target_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="target_id is required when target_type is provided.",
        )

    # Validate that at least one targeting mechanism is provided.
    if (
        payload.symbol is None
        and payload.universe is None
        and payload.target_type is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either symbol, universe, or target_type must be specified.",
        )

    conditions_json = json.dumps(
        [IndicatorCondition.parse_obj(c).dict() for c in payload.conditions],
        default=str,
    )
    action_params_json = json.dumps(payload.action_params or {}, default=str)

    expr_json: str | None = None
    dsl_expr = payload.dsl_expression or None
    if dsl_expr:
        try:
            expr = parse_expression(dsl_expr)
            expr_dict = expression_to_dict(expr)
            expr_json = json.dumps(expr_dict, default=str)
        except IndicatorAlertError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid DSL expression: {exc}",
            ) from exc

    entity = IndicatorRule(
        user_id=user.id,
        strategy_id=payload.strategy_id,
        name=payload.name,
        symbol=payload.symbol,
        universe=payload.universe,
        exchange=payload.exchange,
        target_type=payload.target_type,
        target_id=payload.target_id,
        timeframe=payload.timeframe,
        logic=payload.logic,
        conditions_json=conditions_json,
        expression_json=expr_json,
        dsl_expression=dsl_expr,
        trigger_mode=payload.trigger_mode,
        action_type=payload.action_type,
        action_params_json=action_params_json,
        expires_at=to_utc_or_none(payload.expires_at),
        enabled=payload.enabled,
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return _indicator_rule_to_read(entity)


@router.patch("/{rule_id}", response_model=IndicatorRuleRead)
def update_indicator_rule(
    rule_id: int,
    payload: IndicatorRuleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IndicatorRule:
    """Update selected fields of an indicator rule."""

    import json

    entity = db.get(IndicatorRule, rule_id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    _ensure_owner(entity, user)

    data = payload.dict(exclude_unset=True)

    if (
        "target_type" in data
        and data.get("target_type")
        and not (data.get("target_id") or entity.target_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="target_id is required when target_type is provided.",
        )

    if "conditions" in data:
        from app.schemas.indicator_rules import IndicatorCondition

        conditions = data.pop("conditions") or []
        if not conditions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="conditions cannot be empty",
            )
        entity.conditions_json = json.dumps(
            [IndicatorCondition.parse_obj(c).dict() for c in conditions],
            default=str,
        )

    if "action_params" in data:
        action_params = data.pop("action_params") or {}
        entity.action_params_json = json.dumps(action_params, default=str)

    if "dsl_expression" in data:
        dsl_expr = data.pop("dsl_expression")
        if dsl_expr:
            try:
                expr = parse_expression(dsl_expr)
                expr_dict = expression_to_dict(expr)
                entity.expression_json = json.dumps(expr_dict, default=str)
                entity.dsl_expression = dsl_expr
            except IndicatorAlertError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid DSL expression: {exc}",
                ) from exc
        else:
            # Clearing the DSL expression also clears the compiled AST.
            entity.dsl_expression = None
            entity.expression_json = None

    for field, value in data.items():
        if field == "expires_at":
            setattr(entity, field, to_utc_or_none(value))
            continue
        setattr(entity, field, value)

    db.add(entity)
    db.commit()
    db.refresh(entity)
    return _indicator_rule_to_read(entity)


@router.delete(
    "/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_indicator_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Delete an indicator rule owned by the current user."""

    entity = db.get(IndicatorRule, rule_id)
    if entity is None:
        return

    _ensure_owner(entity, user)
    db.delete(entity)
    db.commit()


__all__ = ["router"]
