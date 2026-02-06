from __future__ import annotations

from datetime import UTC, date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import HoldingsSummarySnapshot, User
from app.schemas.holdings_summary import (
    HoldingsSummarySnapshotRead,
    HoldingsSummarySnapshotsMeta,
)
from app.services.holdings_summary_snapshots import (
    compute_holdings_summary_metrics,
    upsert_holdings_summary_snapshot,
    _as_of_date_ist,
)
from app.core.market_hours import IST_OFFSET

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


@router.post("/snapshots/capture", response_model=HoldingsSummarySnapshotRead)
def capture_holdings_summary_snapshot(
    broker_name: str = Query("zerodha", min_length=1),
    allow_fetch_market_data: bool = Query(False),
    as_of_date: Optional[date] = Query(
        None,
        description=(
            "Optional override for the snapshot's as_of_date. "
            "Used internally to finalize the previous trading day during pre-open."
        ),
    ),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> HoldingsSummarySnapshot:
    """Capture today's holdings summary and persist as a daily snapshot.

    This hits the broker for live holdings (and funds, when available) and
    stores a compact daily row for dashboard trends.
    """

    broker = (broker_name or "").strip().lower()

    today_ist = _as_of_date_ist(datetime.now(UTC))
    target_date = as_of_date or today_ist

    if target_date > today_ist:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"as_of_date cannot be in the future (today IST: {today_ist.isoformat()}).",
        )

    # Correctness guard: capturing a "previous-day final" snapshot after market
    # open will often be contaminated by today's trading activity. Only allow
    # previous-day overrides during a safe pre-open window.
    if target_date < today_ist:
        now_ist_naive = (datetime.now(UTC) + IST_OFFSET).replace(tzinfo=None)
        deadline = now_ist_naive.replace(hour=9, minute=15, second=0, microsecond=0)
        if now_ist_naive >= deadline:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Too late to capture a previous-day snapshot after 09:15 IST. "
                    "Please start SigmaTrader before market open so it can finalize "
                    "yesterday's snapshot safely."
                ),
            )

    # Fetch live holdings via the existing API logic (keeps behavior consistent).
    from app.api import positions as positions_api

    holdings = positions_api.list_holdings(
        broker_name=broker,
        db=db,
        settings=settings,
        user=user,
    )

    funds_available: float | None = None
    if broker == "zerodha":
        from app.api import zerodha as zerodha_api

        margins = zerodha_api.zerodha_margins(db=db, settings=settings, user=user)
        raw = margins.get("available") if isinstance(margins, dict) else None
        try:
            funds_available = float(raw) if raw is not None else None
        except Exception:
            funds_available = None

    metrics = compute_holdings_summary_metrics(
        holdings=holdings,
        funds_available=funds_available,
        settings=settings,
        db=db,
        allow_fetch_market_data=bool(allow_fetch_market_data),
    )

    row = upsert_holdings_summary_snapshot(
        db,
        user_id=int(user.id),
        broker_name=broker,
        as_of_date=target_date,
        metrics=metrics,
    )
    return row


@router.get("/snapshots", response_model=List[HoldingsSummarySnapshotRead])
def list_holdings_summary_snapshots(
    broker_name: str = Query("zerodha", min_length=1),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(2000, ge=1, le=10000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[HoldingsSummarySnapshot]:
    broker = (broker_name or "").strip().lower()
    q = db.query(HoldingsSummarySnapshot).filter(
        HoldingsSummarySnapshot.user_id == int(user.id),
        HoldingsSummarySnapshot.broker_name == broker,
    )
    if start_date is not None:
        q = q.filter(HoldingsSummarySnapshot.as_of_date >= start_date)
    if end_date is not None:
        q = q.filter(HoldingsSummarySnapshot.as_of_date <= end_date)
    return (
        q.order_by(HoldingsSummarySnapshot.as_of_date.asc())  # type: ignore[arg-type]
        .limit(limit)
        .all()
    )



@router.get("/snapshots/meta", response_model=HoldingsSummarySnapshotsMeta)
def holdings_summary_snapshots_meta(
    broker_name: str = Query("zerodha", min_length=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HoldingsSummarySnapshotsMeta:
    broker = (broker_name or "").strip().lower()
    today = _as_of_date_ist(datetime.now(UTC))
    min_date = (
        db.query(HoldingsSummarySnapshot.as_of_date)
        .filter(
            HoldingsSummarySnapshot.user_id == int(user.id),
            HoldingsSummarySnapshot.broker_name == broker,
        )
        .order_by(HoldingsSummarySnapshot.as_of_date.asc())
        .limit(1)
        .scalar()
    )
    max_date = (
        db.query(HoldingsSummarySnapshot.as_of_date)
        .filter(
            HoldingsSummarySnapshot.user_id == int(user.id),
            HoldingsSummarySnapshot.broker_name == broker,
        )
        .order_by(HoldingsSummarySnapshot.as_of_date.desc())
        .limit(1)
        .scalar()
    )
    return HoldingsSummarySnapshotsMeta(
        broker_name=broker,
        today=today,
        min_date=min_date,
        max_date=max_date,
    )


__all__ = ["router"]
