from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user_optional
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.holdings_exit.symbols import normalize_holding_symbol_exchange
from app.models import HoldingExitSubscription, User
from app.schemas.holdings_exit import (
    HoldingExitEventRead,
    HoldingExitSubscriptionCreate,
    HoldingExitSubscriptionPatch,
    HoldingExitSubscriptionRead,
    validate_mvp_create,
    validate_mvp_patch,
)
from app.services.holdings_exit_store import (
    ensure_subscription_owned,
    utc_now,
    write_holding_exit_event,
)

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


def _ensure_enabled(settings: Settings) -> None:
    if not bool(getattr(settings, "holdings_exit_enabled", False)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Holdings exit automation is disabled.",
        )


def _allowlist_ok(settings: Settings, *, exchange: str, symbol: str) -> bool:
    raw = str(getattr(settings, "holdings_exit_allowlist_symbols", "") or "").strip()
    if not raw:
        return True
    allow = set()
    for part in raw.split(","):
        p = part.strip().upper()
        if not p:
            continue
        allow.add(p)
    key = f"{exchange.strip().upper()}:{symbol.strip().upper()}"
    return key in allow or symbol.strip().upper() in allow


def _get_or_404(db: Session, sub_id: int) -> HoldingExitSubscription:
    sub = db.get(HoldingExitSubscription, int(sub_id))
    if sub is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return sub


@router.get("", response_model=list[HoldingExitSubscriptionRead])
def list_subscriptions(
    status_filter: Optional[str] = Query(None, alias="status"),
    broker_name: Optional[str] = Query(None),
    exchange: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
    settings: Settings = Depends(get_settings),
) -> list[HoldingExitSubscription]:
    _ensure_enabled(settings)

    q = db.query(HoldingExitSubscription)
    if user is not None:
        q = q.filter(
            (HoldingExitSubscription.user_id == user.id)
            | (HoldingExitSubscription.user_id.is_(None))
        )
    if status_filter:
        q = q.filter(
            HoldingExitSubscription.status == str(status_filter).strip().upper(),
        )
    if broker_name:
        q = q.filter(
            HoldingExitSubscription.broker_name == str(broker_name).strip().lower()
        )
    if exchange:
        q = q.filter(HoldingExitSubscription.exchange == str(exchange).strip().upper())
    if symbol:
        sym, exch = normalize_holding_symbol_exchange(symbol, exchange)
        if sym:
            q = q.filter(HoldingExitSubscription.symbol == sym)
        if exch:
            q = q.filter(HoldingExitSubscription.exchange == exch)

    return q.order_by(HoldingExitSubscription.created_at.desc()).limit(1000).all()


@router.post("", response_model=HoldingExitSubscriptionRead)
def create_subscription(
    payload: HoldingExitSubscriptionCreate,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
    settings: Settings = Depends(get_settings),
) -> HoldingExitSubscription:
    _ensure_enabled(settings)

    try:
        validate_mvp_create(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    symbol, exchange = normalize_holding_symbol_exchange(
        payload.symbol,
        payload.exchange,
    )
    if not symbol:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="symbol is required.",
        )
    if not _allowlist_ok(settings, exchange=exchange, symbol=symbol):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Holdings exit automation is not enabled for this symbol.",
        )

    broker = (payload.broker_name or "zerodha").strip().lower()
    product = (payload.product or "CNC").strip().upper()

    user_id = user.id if user is not None else None

    # Best-effort de-dupe: exact match on the unique scope key.
    existing = (
        db.query(HoldingExitSubscription)
        .filter(
            HoldingExitSubscription.user_id == user_id,
            HoldingExitSubscription.broker_name == broker,
            HoldingExitSubscription.exchange == exchange,
            HoldingExitSubscription.symbol == symbol,
            HoldingExitSubscription.product == product,
            HoldingExitSubscription.trigger_kind
            == str(payload.trigger_kind).strip().upper(),
            HoldingExitSubscription.trigger_value == float(payload.trigger_value),
            HoldingExitSubscription.size_mode == str(payload.size_mode).strip().upper(),
            HoldingExitSubscription.size_value == float(payload.size_value),
        )
        .one_or_none()
    )
    if existing is not None:
        ensure_subscription_owned(existing, user_id=user_id)
        return existing

    sub = HoldingExitSubscription(
        user_id=user_id,
        broker_name=broker,
        symbol=symbol,
        exchange=exchange,
        product=product,
        trigger_kind=str(payload.trigger_kind).strip().upper(),
        trigger_value=float(payload.trigger_value),
        price_source=str(payload.price_source).strip().upper(),
        size_mode=str(payload.size_mode).strip().upper(),
        size_value=float(payload.size_value),
        min_qty=int(payload.min_qty),
        order_type=str(payload.order_type).strip().upper(),
        dispatch_mode=str(payload.dispatch_mode).strip().upper(),
        execution_target=str(payload.execution_target).strip().upper(),
        status="ACTIVE",
        pending_order_id=None,
        last_error=None,
        last_evaluated_at=None,
        last_triggered_at=None,
        next_eval_at=utc_now(),
        cooldown_seconds=int(payload.cooldown_seconds),
        cooldown_until=None,
        trigger_key=None,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)

    write_holding_exit_event(
        db,
        subscription_id=sub.id,
        event_type="SUB_CREATED",
        details={
            "broker_name": broker,
            "exchange": exchange,
            "symbol": symbol,
            "product": product,
            "trigger_kind": sub.trigger_kind,
            "trigger_value": sub.trigger_value,
            "size_mode": sub.size_mode,
            "size_value": sub.size_value,
        },
    )

    return sub


@router.patch("/{subscription_id}", response_model=HoldingExitSubscriptionRead)
def patch_subscription(
    subscription_id: int,
    payload: HoldingExitSubscriptionPatch,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
    settings: Settings = Depends(get_settings),
) -> HoldingExitSubscription:
    _ensure_enabled(settings)

    try:
        validate_mvp_patch(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    sub = _get_or_404(db, subscription_id)
    user_id = user.id if user is not None else None
    try:
        ensure_subscription_owned(sub, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        ) from exc

    if sub.status not in {"ACTIVE", "PAUSED", "ERROR"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only ACTIVE/PAUSED/ERROR subscriptions can be edited.",
        )

    changed: dict[str, Any] = {}

    def _set(attr: str, val: Any) -> None:
        setattr(sub, attr, val)
        changed[attr] = val

    if payload.trigger_kind is not None:
        _set("trigger_kind", str(payload.trigger_kind).strip().upper())
    if payload.trigger_value is not None:
        _set("trigger_value", float(payload.trigger_value))
    if payload.price_source is not None:
        _set("price_source", str(payload.price_source).strip().upper())

    if payload.size_mode is not None:
        _set("size_mode", str(payload.size_mode).strip().upper())
    if payload.size_value is not None:
        _set("size_value", float(payload.size_value))
    if payload.min_qty is not None:
        _set("min_qty", int(payload.min_qty))

    if payload.dispatch_mode is not None:
        _set("dispatch_mode", str(payload.dispatch_mode).strip().upper())
    if payload.execution_target is not None:
        _set("execution_target", str(payload.execution_target).strip().upper())
    if payload.cooldown_seconds is not None:
        _set("cooldown_seconds", int(payload.cooldown_seconds))

    if not changed:
        return sub

    sub.updated_at = utc_now()
    db.add(sub)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update subscription: {exc}",
        ) from exc
    db.refresh(sub)

    write_holding_exit_event(
        db,
        subscription_id=sub.id,
        event_type="SUB_UPDATED",
        details={"changed": changed},
    )

    return sub


@router.post("/{subscription_id}/pause", response_model=HoldingExitSubscriptionRead)
def pause_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
    settings: Settings = Depends(get_settings),
) -> HoldingExitSubscription:
    _ensure_enabled(settings)
    sub = _get_or_404(db, subscription_id)
    user_id = user.id if user is not None else None
    try:
        ensure_subscription_owned(sub, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        ) from exc

    if sub.status == "COMPLETED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Completed subscriptions cannot be paused.",
        )

    sub.status = "PAUSED"
    sub.updated_at = utc_now()
    db.add(sub)
    db.commit()
    db.refresh(sub)

    write_holding_exit_event(
        db,
        subscription_id=sub.id,
        event_type="SUB_PAUSED",
        details={"reason": "user"},
    )
    return sub


@router.post("/{subscription_id}/resume", response_model=HoldingExitSubscriptionRead)
def resume_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
    settings: Settings = Depends(get_settings),
) -> HoldingExitSubscription:
    _ensure_enabled(settings)
    sub = _get_or_404(db, subscription_id)
    user_id = user.id if user is not None else None
    try:
        ensure_subscription_owned(sub, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        ) from exc

    if sub.status == "COMPLETED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Completed subscriptions cannot be resumed.",
        )

    # Resume semantics (MVP):
    # - clear pending_order_id to avoid accidental re-attachment to an old order
    # - clear last_error so UI shows it's back to normal
    # - schedule immediate evaluation
    sub.status = "ACTIVE"
    sub.pending_order_id = None
    sub.last_error = None
    sub.cooldown_until = None
    sub.next_eval_at = utc_now()
    sub.updated_at = utc_now()

    db.add(sub)
    db.commit()
    db.refresh(sub)

    write_holding_exit_event(
        db,
        subscription_id=sub.id,
        event_type="SUB_RESUMED",
        details={"reason": "user"},
    )
    return sub


@router.delete(
    "/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
    settings: Settings = Depends(get_settings),
) -> None:
    _ensure_enabled(settings)
    sub = _get_or_404(db, subscription_id)
    user_id = user.id if user is not None else None
    try:
        ensure_subscription_owned(sub, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        ) from exc

    db.delete(sub)
    db.commit()
    return None


@router.get("/{subscription_id}/events", response_model=list[HoldingExitEventRead])
def list_events(
    subscription_id: int,
    limit: int = Query(200, ge=1, le=2000),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
    settings: Settings = Depends(get_settings),
) -> list[HoldingExitEventRead]:
    _ensure_enabled(settings)
    sub = _get_or_404(db, subscription_id)
    user_id = user.id if user is not None else None
    try:
        ensure_subscription_owned(sub, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        ) from exc

    from app.models import HoldingExitEvent

    rows = (
        db.query(HoldingExitEvent)
        .filter(HoldingExitEvent.subscription_id == int(subscription_id))
        .order_by(HoldingExitEvent.event_ts.desc())
        .limit(int(limit))
        .all()
    )
    return [HoldingExitEventRead.from_model(r) for r in rows]


__all__ = ["router"]
