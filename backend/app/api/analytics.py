from __future__ import annotations

from datetime import UTC, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import get_current_user_optional
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import AnalyticsTrade, Order, Strategy, User
from app.schemas.analytics import (
    AnalyticsRebuildResponse,
    AnalyticsSummary,
    AnalyticsTradeRead,
)
from app.services.analytics import compute_strategy_analytics, rebuild_trades

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


class AnalyticsSummaryParams(BaseModel):
    strategy_id: Optional[int] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    include_simulated: bool = False


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
    user: User | None = Depends(get_current_user_optional),
) -> AnalyticsSummary:
    """Return basic P&L analytics for a strategy and optional date range."""

    result = compute_strategy_analytics(
        db=db,
        strategy_id=params.strategy_id,
        date_from=params.date_from,
        date_to=params.date_to,
        user_id=user.id if user is not None else None,
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


@router.post("/trades", response_model=List[AnalyticsTradeRead])
def analytics_trades(
    params: AnalyticsSummaryParams,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> List[AnalyticsTradeRead]:
    """Return a list of trades for optional strategy and date filters."""

    query = (
        db.query(AnalyticsTrade, Order, Strategy)
        .join(Order, AnalyticsTrade.entry_order_id == Order.id)
        .outerjoin(Strategy, AnalyticsTrade.strategy_id == Strategy.id)
    )
    if user is not None:
        query = query.filter(
            (Order.user_id == user.id) | (Order.user_id.is_(None)),
        )
    if params.strategy_id is not None:
        query = query.filter(AnalyticsTrade.strategy_id == params.strategy_id)
    if params.date_from is not None:
        query = query.filter(AnalyticsTrade.closed_at >= params.date_from)
    if params.date_to is not None:
        query = query.filter(AnalyticsTrade.closed_at <= params.date_to)

    rows = query.order_by(AnalyticsTrade.closed_at).all()

    trades: List[AnalyticsTradeRead] = []
    for trade, entry_order, strategy in rows:
        trades.append(
            AnalyticsTradeRead(
                id=trade.id,
                strategy_id=trade.strategy_id,
                strategy_name=getattr(strategy, "name", None),
                symbol=entry_order.symbol,
                product=entry_order.product,
                pnl=trade.pnl,
                opened_at=trade.opened_at,
                closed_at=trade.closed_at,
            )
        )
    return trades


__all__ = ["router"]
