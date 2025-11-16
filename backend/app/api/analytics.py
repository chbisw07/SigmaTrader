from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import Order, Strategy
from app.schemas.analytics import AnalyticsRebuildResponse, AnalyticsSummary
from app.services.analytics import compute_strategy_analytics, rebuild_trades

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


class AnalyticsSummaryParams(BaseModel):
    strategy_id: Optional[int] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


@router.post("/rebuild-trades", response_model=AnalyticsRebuildResponse)
def rebuild_trades_endpoint(db: Session = Depends(get_db)) -> AnalyticsRebuildResponse:
    """Rebuild analytics_trades from executed orders.

    This can be called manually or from an offline maintenance task.
    """

    created = rebuild_trades(db)
    return AnalyticsRebuildResponse(created=created)


@router.post(
    "/dev-seed-sample-data",
    response_model=AnalyticsRebuildResponse,
    status_code=status.HTTP_201_CREATED,
)
def dev_seed_sample_data(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AnalyticsRebuildResponse:
    """Seed a few executed orders and rebuild trades (dev only).

    This endpoint is intended for local development when markets are
    closed. It creates a demo strategy and a couple of executed trades
    if they do not already exist, then rebuilds analytics_trades.
    """

    if settings.environment not in {"dev", "local", "test"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dev seed endpoint is not available in this environment.",
        )

    strategy = (
        db.query(Strategy)
        .filter(Strategy.name == "analytics-demo-strategy")
        .one_or_none()
    )
    if strategy is None:
        strategy = Strategy(
            name="analytics-demo-strategy",
            description="Sample strategy for analytics demo",
            execution_mode="AUTO",
            enabled=True,
        )
        db.add(strategy)
        db.commit()
        db.refresh(strategy)

    existing_count = db.query(Order).filter(Order.strategy_id == strategy.id).count()
    if existing_count == 0:
        now = datetime.now(UTC)

        # Winning trade: BUY 10 @ 100 -> SELL 10 @ 110
        buy = Order(
            strategy_id=strategy.id,
            symbol="NSE:INFY",
            exchange="NSE",
            side="BUY",
            qty=10,
            price=100.0,
            order_type="LIMIT",
            product="CNC",
            gtt=False,
            status="EXECUTED",
            mode="AUTO",
            simulated=False,
            created_at=now,
            updated_at=now,
        )
        sell = Order(
            strategy_id=strategy.id,
            symbol="NSE:INFY",
            exchange="NSE",
            side="SELL",
            qty=10,
            price=110.0,
            order_type="LIMIT",
            product="CNC",
            gtt=False,
            status="EXECUTED",
            mode="AUTO",
            simulated=False,
            created_at=now,
            updated_at=now,
        )
        db.add_all([buy, sell])
        db.commit()

    created = rebuild_trades(db, strategy_id=strategy.id)
    return AnalyticsRebuildResponse(created=created)


@router.post("/summary", response_model=AnalyticsSummary)
def analytics_summary(
    params: AnalyticsSummaryParams,
    db: Session = Depends(get_db),
) -> AnalyticsSummary:
    """Return basic P&L analytics for a strategy and optional date range."""

    result = compute_strategy_analytics(
        db=db,
        strategy_id=params.strategy_id,
        date_from=params.date_from,
        date_to=params.date_to,
    )
    return AnalyticsSummary(
        strategy_id=result.strategy_id,
        total_pnl=result.total_pnl,
        trades=result.trades,
        win_rate=result.win_rate,
        avg_win=result.avg_win,
        avg_loss=result.avg_loss,
        max_drawdown=result.max_drawdown,
    )


__all__ = ["router"]
