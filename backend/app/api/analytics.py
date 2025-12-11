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
    CorrelationClusterSummary,
    CorrelationPair,
    HoldingsCorrelationResult,
    SymbolCorrelationStats,
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
    min_weight_fraction: float = Query(
        0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum approximate portfolio weight (0–1) for a holding to be "
            "included in the correlation matrix."
        ),
    ),
    cluster_threshold: float = Query(
        0.6,
        ge=0.0,
        le=1.0,
        description=(
            "Correlation threshold used when grouping holdings into "
            "high-correlation clusters."
        ),
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

    # Aggregate an approximate portfolio value per symbol so that we can
    # (optionally) exclude very small positions from the correlation view
    # and compute cluster weights.
    symbol_values: Dict[str, float] = {}
    symbol_exchange: Dict[str, str] = {}
    ordered_symbols: List[str] = []

    for h in holdings:
        if h.quantity <= 0:
            continue
        symbol = h.symbol
        if not symbol:
            continue
        exchange = (h.exchange or "NSE").upper()
        last_price = h.last_price if h.last_price is not None else h.average_price

        try:
            qty_f = float(h.quantity)
            price_f = float(last_price) if last_price is not None else None
        except (TypeError, ValueError):
            continue

        value = qty_f * price_f if price_f is not None and price_f > 0 else 0.0
        symbol_values[symbol] = symbol_values.get(symbol, 0.0) + value
        if symbol not in symbol_exchange:
            symbol_exchange[symbol] = exchange
        if symbol not in ordered_symbols:
            ordered_symbols.append(symbol)

    if len(symbol_values) < 2:
        return HoldingsCorrelationResult(
            symbols=list(symbol_values.keys()),
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
            symbol_stats=[],
            clusters=[],
            effective_independent_bets=None,
        )

    total_value = sum(symbol_values.values())
    weights_by_symbol: Dict[str, float] = {}
    if total_value > 0:
        for sym, val in symbol_values.items():
            weights_by_symbol[sym] = val / total_value
    else:
        # Fall back to equal weights when we cannot infer a meaningful
        # portfolio value (e.g. missing prices).
        n_syms = len(symbol_values)
        equal_weight = 1.0 / n_syms if n_syms else 0.0
        for sym in symbol_values.keys():
            weights_by_symbol[sym] = equal_weight

    included_symbols: List[str] = []
    for sym in ordered_symbols:
        if sym not in symbol_values:
            continue
        weight = weights_by_symbol.get(sym, 0.0)
        if weight < min_weight_fraction:
            continue
        included_symbols.append(sym)

    if len(included_symbols) < 2:
        return HoldingsCorrelationResult(
            symbols=included_symbols,
            matrix=[],
            window_days=window_days,
            observations=0,
            average_correlation=None,
            diversification_rating="insufficient-data",
            summary=(
                "Not enough holdings above the minimum weight threshold to "
                "compute correlations."
            ),
            recommendations=[
                (
                    "Lower the minimum weight filter or increase position "
                    "sizes so that more holdings participate in the "
                    "diversification analysis."
                ),
            ],
            top_positive=[],
            top_negative=[],
            symbol_stats=[],
            clusters=[],
            effective_independent_bets=None,
        )

    now_ist = datetime.now(UTC) + IST_OFFSET
    end = now_ist.replace(tzinfo=None)
    start = end - timedelta(days=window_days)

    returns_by_symbol: Dict[str, Dict[datetime, float]] = {}
    date_sets: List[set[datetime]] = []

    for symbol in included_symbols:
        exchange = symbol_exchange.get(symbol, "NSE")
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
        return HoldingsCorrelationResult(
            symbols=list(returns_by_symbol.keys()),
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
            symbol_stats=[],
            clusters=[],
            effective_independent_bets=None,
        )

    common_dates = set.intersection(*date_sets)
    if len(common_dates) < 5:
        return HoldingsCorrelationResult(
            symbols=list(returns_by_symbol.keys()),
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
            symbol_stats=[],
            clusters=[],
            effective_independent_bets=None,
        )

    dates_sorted = sorted(common_dates)
    observations = len(dates_sorted)

    symbol_list = sorted(returns_by_symbol.keys())

    # Re-normalise weights on the final symbol set in case some holdings
    # were dropped due to missing history.
    weights_used: Dict[str, float] = {}
    total_weight_used = sum(weights_by_symbol.get(sym, 0.0) for sym in symbol_list)
    if total_weight_used > 0:
        for sym in symbol_list:
            weights_used[sym] = weights_by_symbol.get(sym, 0.0) / total_weight_used
    else:
        n_syms = len(symbol_list)
        equal_weight = 1.0 / n_syms if n_syms else 0.0
        for sym in symbol_list:
            weights_used[sym] = equal_weight
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

    # Correlation-based clusters: treat pairs above cluster_threshold as
    # edges in an undirected graph and compute connected components.
    idx_by_symbol: Dict[str, int] = {sym: i for i, sym in enumerate(symbol_list)}
    adjacency: Dict[str, set[str]] = {sym: set() for sym in symbol_list}
    for sym_i, sym_j, corr in pairs:
        if corr >= cluster_threshold:
            adjacency[sym_i].add(sym_j)
            adjacency[sym_j].add(sym_i)

    raw_clusters: List[List[str]] = []
    visited: set[str] = set()
    for sym in symbol_list:
        if sym in visited:
            continue
        stack = [sym]
        visited.add(sym)
        members: List[str] = []
        while stack:
            current = stack.pop()
            members.append(current)
            for neigh in adjacency[current]:
                if neigh not in visited:
                    visited.add(neigh)
                    stack.append(neigh)
        raw_clusters.append(members)

    def _cluster_weight(symbols: Sequence[str]) -> float:
        return sum(weights_used.get(sym, 0.0) for sym in symbols)

    cluster_label_by_symbol: Dict[str, str] = {}
    cluster_summaries: List[CorrelationClusterSummary] = []

    cluster_name_alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    sorted_clusters = sorted(
        raw_clusters,
        key=lambda members: _cluster_weight(members),
        reverse=True,
    )

    for idx, members in enumerate(sorted_clusters):
        if idx < len(cluster_name_alphabet):
            label = cluster_name_alphabet[idx]
        else:
            label = f"C{idx + 1}"
        for sym in members:
            cluster_label_by_symbol[sym] = label

        internal_corrs: List[float] = []
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                sym_i = members[i]
                sym_j = members[j]
                val = matrix[idx_by_symbol[sym_i]][idx_by_symbol[sym_j]]
                if val is not None:
                    internal_corrs.append(val)

        avg_internal: Optional[float] = None
        if internal_corrs:
            avg_internal = sum(internal_corrs) / len(internal_corrs)

        cross_corrs: List[float] = []
        others = [s for s in symbol_list if s not in members]
        for sym_i in members:
            for sym_j in others:
                val = matrix[idx_by_symbol[sym_i]][idx_by_symbol[sym_j]]
                if val is not None:
                    cross_corrs.append(val)

        avg_to_others: Optional[float] = None
        if cross_corrs:
            avg_to_others = sum(cross_corrs) / len(cross_corrs)

        weight_fraction = _cluster_weight(members)
        cluster_summaries.append(
            CorrelationClusterSummary(
                id=label,
                symbols=members,
                weight_fraction=weight_fraction if weight_fraction > 0 else None,
                average_internal_correlation=avg_internal,
                average_to_others=avg_to_others,
            ),
        )

    # Per-symbol stats combining cluster labels, weights, and local
    # correlation structure.
    symbol_pairs: Dict[str, List[Tuple[str, float]]] = {sym: [] for sym in symbol_list}
    for sym_i, sym_j, corr in pairs:
        symbol_pairs.setdefault(sym_i, []).append((sym_j, corr))
        symbol_pairs.setdefault(sym_j, []).append((sym_i, corr))

    symbol_stats: List[SymbolCorrelationStats] = []
    for sym in symbol_list:
        corrs_for_sym = symbol_pairs.get(sym, [])
        avg_for_sym: Optional[float] = None
        most_sym: Optional[str] = None
        most_val: Optional[float] = None
        if corrs_for_sym:
            values = [c for _, c in corrs_for_sym]
            avg_for_sym = sum(values) / len(values)
            most_sym, most_val = max(corrs_for_sym, key=lambda p: abs(p[1]))
        symbol_stats.append(
            SymbolCorrelationStats(
                symbol=sym,
                average_correlation=avg_for_sym,
                most_correlated_symbol=most_sym,
                most_correlated_value=most_val,
                cluster=cluster_label_by_symbol.get(sym),
                weight_fraction=weights_used.get(sym),
            ),
        )

    # Simple notion of “effective independent bets” based on cluster
    # weights: 1 / sum(w_i^2) where w_i are cluster weights.
    effective_independent_bets: Optional[float] = None
    cluster_weights = [c.weight_fraction or 0.0 for c in cluster_summaries]
    denom = sum(w * w for w in cluster_weights if w > 0)
    if denom > 0:
        effective_independent_bets = 1.0 / denom

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
        symbol_stats=symbol_stats,
        clusters=cluster_summaries,
        effective_independent_bets=effective_independent_bets,
    )


__all__ = ["router"]
