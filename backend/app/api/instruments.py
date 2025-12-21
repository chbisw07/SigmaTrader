from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import SystemEvent, User
from app.services.instruments_sync import (
    sync_smartapi_instrument_master,
    sync_zerodha_instrument_master,
)

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


@router.post("/sync", response_model=Dict[str, Any])
def sync_instruments(
    broker_name: str = Query("zerodha", min_length=1),
    limit: int | None = Query(None, ge=1, le=50000),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Manually trigger instrument master sync for a broker."""

    _ = user
    broker = (broker_name or "").strip().lower()
    try:
        if broker == "zerodha":
            return sync_zerodha_instrument_master(db, settings)
        if broker == "angelone":
            return sync_smartapi_instrument_master(db, settings, limit=limit)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported broker for instrument sync: {broker}",
    )


@router.get("/status", response_model=Dict[str, Any])
def instruments_status(
    broker_name: str = Query("zerodha", min_length=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return last instrument sync event for a broker (best-effort)."""

    _ = user
    broker = (broker_name or "").strip().lower()

    ev: SystemEvent | None = (
        db.query(SystemEvent)
        .filter(
            SystemEvent.category == "instruments",
            SystemEvent.details_json.ilike(f"%{broker}%"),
        )
        .order_by(SystemEvent.created_at.desc())
        .first()
    )
    if ev is None:
        return {"broker": broker, "last_synced_at": None}
    return {"broker": broker, "last_synced_at": ev.created_at.isoformat()}


__all__ = ["router"]
