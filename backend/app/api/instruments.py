from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import case, or_
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import BrokerInstrument, Listing, SystemEvent, User
from app.services.instruments_sync import (
    sync_smartapi_instrument_master,
    sync_zerodha_instrument_master,
)

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


class InstrumentSearchResult(BaseModel):
    symbol: str
    exchange: str
    tradingsymbol: str
    name: str | None = None
    token: str | None = None


@router.get("/search", response_model=List[InstrumentSearchResult])
def search_instruments(
    q: str = Query(..., min_length=1),
    broker_name: str = Query("zerodha", min_length=1),
    limit: int = Query(20, ge=1, le=50),
    exchange: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[InstrumentSearchResult]:
    """Search the broker instrument master by symbol/name (case-insensitive)."""

    _ = user
    query = (q or "").strip()
    if not query:
        return []
    broker = (broker_name or "").strip().lower() or "zerodha"
    exch = (exchange or "").strip().upper() or None

    q_like = f"%{query}%"
    q_prefix = f"{query}%"

    base = (
        db.query(Listing, BrokerInstrument)
        .join(BrokerInstrument, BrokerInstrument.listing_id == Listing.id)
        .filter(
            Listing.active.is_(True),
            BrokerInstrument.active.is_(True),
            BrokerInstrument.broker_name == broker,
        )
    )
    if exch:
        base = base.filter(Listing.exchange == exch)

    base = base.filter(
        or_(
            Listing.symbol.ilike(q_like),
            Listing.name.ilike(q_like),
            BrokerInstrument.broker_symbol.ilike(q_like),
        )
    )

    # Prefer prefix matches on symbol/tradingsymbol/name.
    rank = case(
        (Listing.symbol.ilike(q_prefix), 0),
        (BrokerInstrument.broker_symbol.ilike(q_prefix), 1),
        (Listing.name.ilike(q_prefix), 2),
        else_=3,
    )

    rows = base.order_by(rank.asc(), Listing.symbol.asc()).limit(limit).all()
    out: list[InstrumentSearchResult] = []
    for listing, bi in rows:
        out.append(
            InstrumentSearchResult(
                symbol=str(listing.symbol),
                exchange=str(listing.exchange),
                tradingsymbol=str(bi.broker_symbol),
                name=getattr(listing, "name", None),
                token=str(getattr(bi, "instrument_token", "") or "") or None,
            )
        )
    return out


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
