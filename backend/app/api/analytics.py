from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import get_current_user_optional
from app.core.config import Settings, get_settings
from app.core.market_hours import IST_OFFSET
from app.db.session import get_db
from app.models import AnalyticsTrade, Order, Strategy, User
from app.schemas.analytics import (
    AnalyticsRebuildResponse,
    AnalyticsSummary,
    AnalyticsTradeRead,
    CorrelationPair,
    HoldingsCorrelationResult,
)
from app.services.analytics import compute_strategy_analytics, rebuild_trades
from app.services.market_data import Timeframe, load_series

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


def _compute_pearson_corr(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n == 0 or n != len(ys):
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = 0.0
    denom_x = 0.0
    denom_y = 0.0
    for x, y in zip(xs, ys, strict=False):
        dx = x - mean_x
        dy = y - mean_y
        num += dx * dy
        denom_x += dx * dx
        denom_y += dy * dy
    if denom_x <= 0 or denom_y <= 0:
        return None
    return num / (denom_x**0.5 * denom_y**0.5)


@router.get(
    "/holdings-correlation",
    response_model=HoldingsCorrelationResult,
)
def holdings_correlation(
    window_days: int = Query(
        90,
        ge=30,
        le=730,
        description="Lookback window for daily returns in calendar days.",
    ),
    timeframe: Timeframe = Query(
        "1d",
        description="Timeframe for correlation calculation (currently 1d only).",
    ),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_current_user_optional),
) -> HoldingsCorrelationResult:
    """Compute a holdings return correlation matrix and diversification summary.

    Uses daily percentage returns over the requested window for the
    current user's live holdings. When data is insufficient, returns an
    empty matrix with explanatory summary text.
    """

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    # Lazy import to avoid circular imports at startup.
    from app.api.positions import list_holdings

    holdings = list_holdings(db=db, settings=settings, user=user)
    symbols_exchanges: List[Tuple[str, str]] = []
    for h in holdings:
        if h.quantity <= 0:
            continue
        symbol = h.symbol
        exchange = (h.exchange or "NSE").upper()
        symbols_exchanges.append((symbol, exchange))

    # Deduplicate symbols while preserving order.
    seen: set[Tuple[str, str]] = set()
    unique_symbols: List[Tuple[str, str]] = []
    for pair in symbols_exchanges:
        if pair not in seen:
            seen.add(pair)
            unique_symbols.append(pair)

    if len(unique_symbols) < 2:
        return HoldingsCorrelationResult(
            symbols=[s for s, _ in unique_symbols],
            matrix=[],
            window_days=window_days,
            observations=0,
            average_correlation=None,
            diversification_rating="insufficient-data",
            summary=(
                "Not enough holdings with valid price history to compute "
                "correlations."
            ),
            recommendations=[
                (
                    "Add more symbols to your portfolio or widen the time "
                    "window to see diversification analysis."
                ),
            ],
            top_positive=[],
            top_negative=[],
        )

    now_ist = datetime.now(UTC) + IST_OFFSET
    end = now_ist.replace(tzinfo=None)
    start = end - timedelta(days=window_days)

    returns_by_symbol: Dict[str, Dict[datetime, float]] = {}
    date_sets: List[set[datetime]] = []

    for symbol, exchange in unique_symbols:
        rows = load_series(
            db,
            settings,
            symbol=symbol,
            exchange=exchange,
            timeframe=timeframe,
            start=start,
            end=end,
        )
        closes: List[float] = [float(r["close"]) for r in rows]
        ts_list: List[datetime] = [r["ts"] for r in rows]
        if len(closes) < 2:
            continue

        series: Dict[datetime, float] = {}
        for i in range(1, len(closes)):
            prev = closes[i - 1]
            curr = closes[i]
            if prev == 0:
                continue
            ret = (curr - prev) / prev
            ts = ts_list[i]
            series[ts] = ret

        if len(series) < 5:
            continue

        returns_by_symbol[symbol] = series
        date_sets.append(set(series.keys()))

    if len(returns_by_symbol) < 2 or not date_sets:
        syms = list(returns_by_symbol.keys())
        return HoldingsCorrelationResult(
            symbols=syms,
            matrix=[],
            window_days=window_days,
            observations=0,
            average_correlation=None,
            diversification_rating="insufficient-data",
            summary=(
                "Historical price data is too sparse to compute a reliable "
                "correlation matrix."
            ),
            recommendations=[
                (
                    "Try increasing the lookback window or ensure market "
                    "data is synced for your holdings."
                ),
            ],
            top_positive=[],
            top_negative=[],
        )

    common_dates = set.intersection(*date_sets)
    if len(common_dates) < 5:
        syms = list(returns_by_symbol.keys())
        return HoldingsCorrelationResult(
            symbols=syms,
            matrix=[],
            window_days=window_days,
            observations=len(common_dates),
            average_correlation=None,
            diversification_rating="insufficient-data",
            summary=(
                "Holdings do not share enough overlapping history in the "
                "selected window to compute correlations."
            ),
            recommendations=[
                (
                    "Try increasing the lookback window or focus on a more "
                    "stable subset of symbols."
                ),
            ],
            top_positive=[],
            top_negative=[],
        )

    dates_sorted = sorted(common_dates)
    observations = len(dates_sorted)

    symbol_list = sorted(returns_by_symbol.keys())
    vectors: Dict[str, List[float]] = {}
    for symbol in symbol_list:
        series = returns_by_symbol[symbol]
        vectors[symbol] = [series[d] for d in dates_sorted]

    matrix: List[List[Optional[float]]] = []
    pairs: List[Tuple[str, str, float]] = []

    for i, sym_i in enumerate(symbol_list):
        row: List[Optional[float]] = []
        for j, sym_j in enumerate(symbol_list):
            if i == j:
                corr = 1.0
            else:
                corr_val = _compute_pearson_corr(vectors[sym_i], vectors[sym_j])
                corr = corr_val
                if corr_val is not None and i < j:
                    pairs.append((sym_i, sym_j, corr_val))
            row.append(corr)
        matrix.append(row)

    avg_corr: Optional[float] = None
    if pairs:
        avg_corr = sum(c for _, _, c in pairs) / len(pairs)

    # Build diversification rating and recommendations.
    rating: str
    summary: str
    recommendations: List[str] = []

    if avg_corr is None:
        rating = "insufficient-data"
        summary = (
            "Could not compute an average correlation for your holdings in this window."
        )
        recommendations.append(
            (
                "Try increasing the lookback window or verify that market "
                "data is available for all holdings."
            ),
        )
    else:
        if avg_corr >= 0.75:
            rating = "very-concentrated"
            summary = (
                f"Average pairwise correlation is {avg_corr:.2f}, indicating a "
                "highly concentrated portfolio where many holdings move together."
            )
            recommendations.extend(
                [
                    (
                        "Consider reducing exposure to the most highly "
                        "correlated holdings, especially if they are large "
                        "weights."
                    ),
                    (
                        "Add positions from sectors, factors, or asset "
                        "classes that behave differently from your current "
                        "core holdings."
                    ),
                ],
            )
        elif avg_corr >= 0.5:
            rating = "concentrated"
            summary = (
                f"Average pairwise correlation is {avg_corr:.2f}, suggesting a "
                "moderately concentrated portfolio."
            )
            recommendations.extend(
                [
                    (
                        "Monitor correlated clusters of holdings; a shock to "
                        "one name may affect the others."
                    ),
                    (
                        "Incrementally add lower-correlation names to improve "
                        "diversification."
                    ),
                ],
            )
        elif avg_corr >= 0.25:
            rating = "moderately-diversified"
            summary = (
                f"Average pairwise correlation is {avg_corr:.2f}, indicating a "
                "moderately diversified portfolio."
            )
            recommendations.extend(
                [
                    (
                        "Diversification is reasonable, but there may still "
                        "be pockets of high correlation."
                    ),
                    (
                        "You can selectively tilt towards low-correlation "
                        "opportunities without overcomplicating the "
                        "portfolio."
                    ),
                ],
            )
        else:
            rating = "well-diversified"
            summary = (
                f"Average pairwise correlation is {avg_corr:.2f}, indicating a "
                "well diversified set of holdings."
            )
            recommendations.extend(
                [
                    (
                        "Your holdings show relatively low co-movement; this "
                        "can help smooth portfolio volatility."
                    ),
                    (
                        "Focus on position sizing and individual risk rather "
                        "than further diversification."
                    ),
                ],
            )

    # Top positively and negatively correlated pairs for context.
    top_positive: List[CorrelationPair] = []
    top_negative: List[CorrelationPair] = []
    if pairs:
        sorted_pos = sorted(
            [p for p in pairs if p[2] > 0],
            key=lambda x: x[2],
            reverse=True,
        )
        sorted_neg = sorted(
            [p for p in pairs if p[2] < 0],
            key=lambda x: x[2],
        )
        for sym_i, sym_j, corr in sorted_pos[:5]:
            top_positive.append(
                CorrelationPair(symbol_x=sym_i, symbol_y=sym_j, correlation=corr),
            )
        for sym_i, sym_j, corr in sorted_neg[:5]:
            top_negative.append(
                CorrelationPair(symbol_x=sym_i, symbol_y=sym_j, correlation=corr),
            )

    return HoldingsCorrelationResult(
        symbols=symbol_list,
        matrix=matrix,
        window_days=window_days,
        observations=observations,
        average_correlation=avg_corr,
        diversification_rating=rating,
        summary=summary,
        recommendations=recommendations,
        top_positive=top_positive,
        top_negative=top_negative,
    )


__all__ = ["router"]
