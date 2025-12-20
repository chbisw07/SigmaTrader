from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, func, tuple_
from sqlalchemy.orm import Session

from app.api.auth import get_current_user_optional
from app.core.config import Settings, get_settings
from app.core.market_hours import IST_OFFSET
from app.db.session import get_db
from app.models import AnalyticsTrade, Candle, Group, GroupMember, Order, Strategy, User
from app.schemas.alerts_v3 import AlertVariableDef
from app.schemas.analytics import (
    AnalyticsRebuildResponse,
    AnalyticsSummary,
    AnalyticsTradeRead,
    CorrelationClusterSummary,
    CorrelationPair,
    HoldingsCorrelationResult,
    RiskSizingRequest,
    RiskSizingResponse,
    SymbolCorrelationStats,
)
from app.services.alerts_v3_compiler import (
    compile_alert_expression_parts,
    compile_custom_indicators_for_user,
)
from app.services.alerts_v3_expression import (
    _EVENT_ALIASES,
    CallNode,
    ComparisonNode,
    EventNode,
    ExprNode,
    LogicalNode,
    NotNode,
    NumberNode,
    _eval_numeric,
)
from app.services.analytics import compute_strategy_analytics, rebuild_trades
from app.services.market_data import (
    Timeframe,
    ensure_history,
    ensure_history_window,
    load_series,
)
from app.services.risk_sizing import compute_risk_position_size

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()

_BASKET_RANGE_DAYS: Dict[str, int] = {
    "1d": 1,
    "1w": 7,
    "1m": 30,
    "3m": 90,
    "6m": 180,
    "1y": 365,
    "2y": 730,
}


class AnalyticsSummaryParams(BaseModel):
    strategy_id: Optional[int] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    include_simulated: bool = False


@router.post("/risk-sizing", response_model=RiskSizingResponse)
def risk_sizing_endpoint(payload: RiskSizingRequest) -> RiskSizingResponse:
    """Compute risk-based position size from entry, stop, and risk budget.

    This is a pure helper that does not touch the database. It is
    intended for frontend tools and strategies to size positions based
    on a maximum per-trade loss.
    """

    try:
        result = compute_risk_position_size(
            entry_price=payload.entry_price,
            stop_price=payload.stop_price,
            risk_budget=payload.risk_budget,
            max_qty=payload.max_qty,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return RiskSizingResponse(
        qty=result.qty,
        notional=result.notional,
        risk_per_share=result.risk_per_share,
        max_loss=result.max_loss,
    )


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


class BasketIndexRequest(BaseModel):
    include_holdings: bool = True
    group_ids: List[int] = []
    range: str = "6m"  # 1d/1w/1m/3m/6m/ytd/1y/2y
    base: float = 100.0


class BasketIndexPoint(BaseModel):
    ts: str  # ISO date string
    value: float
    used_symbols: int
    total_symbols: int


class BasketIndexSeries(BaseModel):
    key: str
    label: str
    points: List[BasketIndexPoint]
    missing_symbols: int
    needs_hydrate_history_symbols: int = 0


class BasketIndexResponse(BaseModel):
    start: datetime
    end: datetime
    series: List[BasketIndexSeries]


def _now_ist_naive() -> datetime:
    return (datetime.now(UTC) + IST_OFFSET).replace(tzinfo=None)


def _compute_equal_weight_index(
    closes_by_symbol: Dict[str, Dict[datetime, float]],
    *,
    base: float,
) -> Tuple[List[Tuple[datetime, float, int, int]], int]:
    symbols = sorted(closes_by_symbol.keys())
    all_dates: List[datetime] = sorted(
        {d for m in closes_by_symbol.values() for d in m.keys()}
    )
    if not all_dates or not symbols:
        return [], len(symbols)

    last_close: Dict[str, float] = {}
    idx = base
    points: List[Tuple[datetime, float, int, int]] = []

    # Initialize on first date using coverage only (no returns).
    first_date = all_dates[0]
    for sym in symbols:
        c = closes_by_symbol[sym].get(first_date)
        if c is not None:
            last_close[sym] = c
    points.append((first_date, idx, len(last_close), len(symbols)))

    for dt in all_dates[1:]:
        used = 0
        ret_sum = 0.0
        for sym in symbols:
            today = closes_by_symbol[sym].get(dt)
            if today is None:
                continue
            prev = last_close.get(sym)
            last_close[sym] = today
            if prev is None or prev == 0:
                continue
            used += 1
            ret_sum += (today - prev) / prev
        if used > 0:
            idx *= 1.0 + (ret_sum / used)
        points.append((dt, idx, used, len(symbols)))

    missing_symbols = len(symbols) - len(last_close)
    return points, missing_symbols


def _clamp_range(now: datetime, range_key: str) -> tuple[datetime, datetime]:
    range_key = (range_key or "").strip().lower()
    if range_key == "ytd":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, now
    days = _BASKET_RANGE_DAYS.get(range_key)
    if days is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid range. Use 1d/1w/1m/3m/6m/ytd/1y/2y.",
        )
    # For daily candles, users expect "1D" to include at least two candles
    # (yesterday + today). We also floor the start to midnight so we don't
    # accidentally exclude the first day candle due to the current time-of-day.
    lookback_days = days
    if range_key == "1d":
        lookback_days = 2
    start = now - timedelta(days=lookback_days)
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, now


def _gap_days(a: datetime | None, b: datetime | None) -> int:
    if a is None or b is None:
        return 0
    return max(0, (b.date() - a.date()).days)


def _big_gap_threshold_days(requested_days: int) -> int:
    """Heuristic for 'big gap' detection relative to the requested window."""

    if requested_days <= 0:
        return 7
    # For a 1M window, a 10-day head gap is meaningful; for 6M+, 60 days.
    return max(7, min(60, requested_days // 3))


def _normalize_symbol_exchange(symbol: str, exchange: str | None) -> tuple[str, str]:
    sym = (symbol or "").strip().upper()
    exch = (exchange or "NSE").strip().upper() or "NSE"
    if ":" in sym:
        prefix, rest = sym.split(":", 1)
        if prefix in {"NSE", "BSE", "NFO", "MCX"} and rest.strip():
            exch = prefix
            sym = rest.strip().upper()
    return sym, exch


def _load_global_min_ts_by_symbol(
    db: Session,
    *,
    timeframe: str,
    pairs: list[tuple[str, str]],
) -> dict[tuple[str, str], datetime]:
    """Return earliest known candle per symbol+exchange for a timeframe.

    Used to distinguish "true missing history" from "late entrant" symbols
    whose earliest available candle itself is after the requested window start.
    """

    if not pairs:
        return {}
    rows = (
        db.query(Candle.symbol, Candle.exchange, func.min(Candle.ts))
        .filter(
            Candle.timeframe == timeframe,
            tuple_(Candle.symbol, Candle.exchange).in_(pairs),
        )
        .group_by(Candle.symbol, Candle.exchange)
        .all()
    )
    out: dict[tuple[str, str], datetime] = {}
    for sym, exch, ts in rows:
        if ts is None:
            continue
        out[(sym, exch)] = ts
    return out


def _maybe_hydrate_tail_gap(
    db: Session,
    settings: Settings,
    *,
    symbol: str,
    exchange: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    max_days: int,
) -> bool:
    """Auto-hydrate small tail gaps (last N days) to keep data fresh."""

    existing_max: datetime | None = (
        db.query(func.max(Candle.ts))
        .filter(
            Candle.symbol == symbol,
            Candle.exchange == exchange,
            Candle.timeframe == timeframe,
            and_(Candle.ts >= start, Candle.ts <= end),
        )
        .scalar()
    )
    if existing_max is None:
        return False
    gap = _gap_days(existing_max, end)
    if gap <= 0 or gap > max_days:
        return False
    # Use `ensure_history` (min/max extension) to avoid re-fetching the entire
    # tail window when only a few forward days are missing.
    ensure_history(
        db,
        settings,
        symbol=symbol,
        exchange=exchange,
        base_timeframe=timeframe,
        start=end - timedelta(days=max_days),
        end=end,
    )
    return True


@router.post("/basket-indices", response_model=BasketIndexResponse)
def basket_indices(
    payload: BasketIndexRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_current_user_optional),
) -> BasketIndexResponse:
    """Compute simple equal-weight index series for holdings and/or groups.

    Indices are based on daily close candles available in the local DB.
    Market-data backfills are disabled here to keep the dashboard responsive.
    """

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    now = _now_ist_naive()
    start, end = _clamp_range(now, payload.range)
    requested_days = _gap_days(start, end)
    big_gap_days = _big_gap_threshold_days(requested_days)

    # Resolve universes.
    universes: List[Tuple[str, str, List[Tuple[str, str]]]] = []
    holdings_members: list[tuple[str, str]] = []
    group_members: list[tuple[str, str]] = []
    if payload.include_holdings:
        try:
            from app.api.positions import list_holdings

            holdings = list_holdings(db=db, settings=settings, user=user)
        except Exception:
            holdings = []
        members = []
        for h in holdings:
            if not h.symbol or not h.quantity or h.quantity <= 0:
                continue
            sym, exch = _normalize_symbol_exchange(
                h.symbol, getattr(h, "exchange", None)
            )
            if not sym:
                continue
            members.append((sym, exch))
        holdings_members = members[:]
        universes.append(("holdings", "Holdings (Zerodha)", members))

    if payload.group_ids:
        groups: List[Group] = (
            db.query(Group)
            .filter(Group.id.in_(payload.group_ids))
            .order_by(Group.name.asc())
            .all()
        )
        for g in groups:
            members = (
                db.query(GroupMember)
                .filter(GroupMember.group_id == g.id)
                .order_by(GroupMember.created_at.asc())
                .all()
            )
            symbols = [
                _normalize_symbol_exchange(m.symbol, m.exchange)
                for m in members
                if m.symbol
            ]
            group_members.extend(symbols)
            universes.append((f"group:{g.id}", g.name, symbols))

    # Load candles for all symbols (deduped).
    uniq: Dict[Tuple[str, str], Dict[datetime, float]] = {}
    for _key, _label, members in universes:
        for sym, exch in members:
            uniq.setdefault((sym, exch), {})

    global_min_map = _load_global_min_ts_by_symbol(
        db,
        timeframe="1d",
        pairs=sorted(uniq.keys()),
    )

    # Data freshness policy on Refresh:
    # - For holdings symbols: ensure requested window is present (min/max extension).
    #   This should prevent "hydrate needed" surprises for holdings.
    # - For group symbols: auto-fill small recent tail gaps; big gaps remain explicit.
    holding_set = set(holdings_members)
    allow_full_fetch = requested_days <= 60
    for sym, exch in uniq.keys():
        try:
            if allow_full_fetch or (sym, exch) in holding_set:
                ensure_history(
                    db,
                    settings,
                    symbol=sym,
                    exchange=exch,
                    base_timeframe="1d",
                    start=start,
                    end=end,
                )
            else:
                _maybe_hydrate_tail_gap(
                    db,
                    settings,
                    symbol=sym,
                    exchange=exch,
                    timeframe="1d",
                    start=start,
                    end=end,
                    max_days=60,
                )
        except Exception:
            # If a symbol cannot be hydrated (e.g. missing instrument token),
            # keep dashboard responsive and let "Hydrate universe" surface details.
            pass

    for sym, exch in uniq.keys():
        candles = load_series(
            db,
            settings,
            symbol=sym,
            exchange=exch,
            timeframe="1d",  # type: ignore[arg-type]
            start=start,
            end=end,
            allow_fetch=False,
        )
        uniq[(sym, exch)] = {c["ts"]: float(c["close"]) for c in candles if c.get("ts")}

    # Build per-universe indices.
    out_series: List[BasketIndexSeries] = []
    for key, label, members in universes:
        closes_by_symbol: Dict[str, Dict[datetime, float]] = {}
        needs_hydrate_history = 0
        for sym, exch in members:
            series = uniq.get((sym, exch), {})
            closes_by_symbol[f"{exch}:{sym}"] = series
            if not series:
                needs_hydrate_history += 1
                continue
            first = min(series.keys())
            if _gap_days(start, first) > big_gap_days:
                global_min = global_min_map.get((sym, exch))
                if global_min is None:
                    needs_hydrate_history += 1
                else:
                    # Late entrant / limited-history: earliest known candle is itself
                    # after the window start, so hydrating more can't fix it.
                    if global_min <= start + timedelta(days=big_gap_days):
                        needs_hydrate_history += 1

        points, missing = _compute_equal_weight_index(
            closes_by_symbol,
            base=float(payload.base or 100.0),
        )
        out_series.append(
            BasketIndexSeries(
                key=key,
                label=label,
                missing_symbols=missing,
                needs_hydrate_history_symbols=needs_hydrate_history,
                points=[
                    BasketIndexPoint(
                        ts=dt.date().isoformat(),
                        value=float(val),
                        used_symbols=int(used),
                        total_symbols=int(total),
                    )
                    for dt, val, used, total in points
                ],
            )
        )

    return BasketIndexResponse(start=start, end=end, series=out_series)


class HydrateUniverseRequest(BaseModel):
    include_holdings: bool = True
    group_ids: List[int] = []
    range: str = "6m"  # 1d/1w/1m/3m/6m/ytd/1y/2y
    timeframe: str = "1d"


class HydrateUniverseResponse(BaseModel):
    hydrated: int
    failed: int
    errors: List[str] = []


@router.post("/hydrate-history", response_model=HydrateUniverseResponse)
def hydrate_history(
    payload: HydrateUniverseRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_current_user_optional),
) -> HydrateUniverseResponse:
    """Fetch and persist missing candle history for a universe (explicit action).

    This endpoint is intended for "big gaps" backfills that the UI triggers
    explicitly via a "Hydrate now" button.
    """

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    tf = (payload.timeframe or "1d").strip().lower()
    if tf != "1d":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only 1d timeframe is supported for hydration on dashboard.",
        )

    now = _now_ist_naive()
    start, end = _clamp_range(now, payload.range)

    members: list[tuple[str, str]] = []
    if payload.include_holdings:
        from app.api.positions import list_holdings

        holdings = list_holdings(db=db, settings=settings, user=user)
        for h in holdings:
            if not h.symbol or not h.quantity or h.quantity <= 0:
                continue
            sym, exch = _normalize_symbol_exchange(
                h.symbol, getattr(h, "exchange", None)
            )
            if not sym:
                continue
            members.append((sym, exch))

    if payload.group_ids:
        groups: List[Group] = (
            db.query(Group)
            .filter(Group.id.in_(payload.group_ids))
            .order_by(Group.name.asc())
            .all()
        )
        allowed = {g.id for g in groups if g.owner_id is None or g.owner_id == user.id}
        if allowed:
            rows: List[GroupMember] = (
                db.query(GroupMember)
                .filter(
                    GroupMember.group_id.in_(sorted(allowed))  # type: ignore[arg-type]
                )
                .all()
            )
            for r in rows:
                if not r.symbol:
                    continue
                sym, exch = _normalize_symbol_exchange(r.symbol, r.exchange)
                if not sym:
                    continue
                members.append((sym, exch))

    uniq: list[tuple[str, str]] = sorted(set(members))
    hydrated = 0
    errors: list[str] = []
    for sym, exch in uniq:
        try:
            ensure_history_window(
                db,
                settings,
                symbol=sym,
                exchange=exch,
                base_timeframe=tf,
                start=start,
                end=end,
            )
            hydrated += 1
        except Exception as exc:  # pragma: no cover - network/provider
            errors.append(f"{exch}:{sym}: {exc}")

    return HydrateUniverseResponse(
        hydrated=hydrated,
        failed=len(errors),
        errors=errors[:30],
    )


class SymbolSeriesRequest(BaseModel):
    symbol: str
    exchange: str = "NSE"
    range: str = "6m"  # 1w/1m/3m/6m/ytd/1y/2y
    timeframe: str = "1d"
    hydrate_mode: str = "auto"  # none|auto|force


class SymbolSeriesPoint(BaseModel):
    ts: str  # ISO date string (date-only)
    open: float
    high: float
    low: float
    close: float
    volume: float


class SymbolSeriesResponse(BaseModel):
    symbol: str
    exchange: str
    start: datetime
    end: datetime
    points: List[SymbolSeriesPoint]
    local_first: datetime | None = None
    local_last: datetime | None = None
    head_gap_days: int = 0
    tail_gap_days: int = 0
    needs_hydrate_history: bool = False


def _model_dump(obj) -> dict:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()  # type: ignore[attr-defined]
    return obj.dict()  # type: ignore[attr-defined]


class _InMemoryCandleCache:
    """Minimal CandleCache-compatible wrapper for historical per-bar evaluation."""

    def __init__(self, *, symbol: str, exchange: str, candles: list[dict]) -> None:
        self.symbol = symbol
        self.exchange = exchange
        self._candles = candles
        self._end = len(candles) - 1

        self._opens = [float(c["open"]) for c in candles]
        self._highs = [float(c["high"]) for c in candles]
        self._lows = [float(c["low"]) for c in candles]
        self._closes = [float(c["close"]) for c in candles]
        self._volumes = [float(c.get("volume") or 0.0) for c in candles]

    def set_end(self, idx: int) -> None:
        self._end = max(0, min(idx, len(self._candles) - 1))

    def candles(self, tf: str) -> list[dict]:
        tf = (tf or "").strip().lower()
        if tf != "1d":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Symbol explorer indicators/signals currently support 1d only.",
            )
        end = self._end
        return self._candles[: end + 1] if self._candles else []

    def series(self, tf: str, source: str) -> tuple[list[float], datetime | None]:
        tf = (tf or "").strip().lower()
        if tf != "1d":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Symbol explorer indicators/signals currently support 1d only.",
            )

        source = (source or "").strip().lower()
        values: list[float]
        if source == "open":
            values = self._opens
        elif source == "high":
            values = self._highs
        elif source == "low":
            values = self._lows
        elif source == "close":
            values = self._closes
        elif source == "volume":
            values = self._volumes
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported source '{source}'.",
            )

        end = self._end
        bar_time = self._candles[end]["ts"] if self._candles else None
        return values[: end + 1], bar_time


class SymbolIndicatorsRequest(BaseModel):
    symbol: str
    exchange: str = "NSE"
    range: str = "6m"
    timeframe: str = "1d"
    hydrate_mode: str = "auto"  # none|auto|force
    variables: List[AlertVariableDef] = []


class SymbolIndicatorsResponse(BaseModel):
    symbol: str
    exchange: str
    start: datetime
    end: datetime
    ts: List[str]
    series: Dict[str, List[Optional[float]]]
    errors: Dict[str, str] = {}


@router.post("/symbol-indicators", response_model=SymbolIndicatorsResponse)
def symbol_indicators(
    payload: SymbolIndicatorsRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_current_user_optional),
) -> SymbolIndicatorsResponse:
    """Compute indicator series for a symbol over the requested window."""

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    sym, exch = _normalize_symbol_exchange(payload.symbol, payload.exchange)
    now = _now_ist_naive()
    start, end = _clamp_range(now, payload.range)

    hydrate_mode = (payload.hydrate_mode or "auto").strip().lower()
    tf = (payload.timeframe or "1d").strip().lower()
    if tf != "1d":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only 1d timeframe is supported for symbol indicators (currently).",
        )

    if hydrate_mode == "force":
        ensure_history_window(
            db,
            settings,
            symbol=sym,
            exchange=exch,
            base_timeframe=tf,
            start=start,
            end=end,
        )
    elif hydrate_mode == "auto":
        # Single symbol: best-effort ensure history so overlays can compute.
        try:
            ensure_history(
                db,
                settings,
                symbol=sym,
                exchange=exch,
                base_timeframe=tf,
                start=start,
                end=end,
            )
        except Exception:
            pass

    candles = load_series(
        db,
        settings,
        symbol=sym,
        exchange=exch,
        timeframe="1d",  # type: ignore[arg-type]
        start=start,
        end=end,
        allow_fetch=False,
    )
    if not candles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No candles found for this symbol in the requested window.",
        )

    custom_indicators = compile_custom_indicators_for_user(
        db, user_id=user.id, dsl_profile=settings.dsl_profile
    )

    raw_vars = [_model_dump(v) for v in (payload.variables or [])]
    # Compile variables (condition is a harmless constant).
    _cond_ast, _cadence, var_map = compile_alert_expression_parts(
        db,
        user_id=user.id,
        variables=raw_vars,
        condition_dsl="1 > 0",
        evaluation_cadence="1d",
        custom_indicators=custom_indicators,
        dsl_profile=settings.dsl_profile,
    )

    # Build a name map preserving the user's casing when possible.
    name_map: dict[str, str] = {}
    for v in payload.variables or []:
        if not (v.name or "").strip():
            continue
        name_map[v.name.strip().upper()] = v.name.strip()

    cache = _InMemoryCandleCache(symbol=sym, exchange=exch, candles=candles)
    ts = [c["ts"].date().isoformat() for c in candles if c.get("ts")]
    n = len(ts)

    out: Dict[str, List[Optional[float]]] = {}
    errors: Dict[str, str] = {}

    for var_upper, expr in var_map.items():
        display = name_map.get(var_upper, var_upper)
        values: List[Optional[float]] = [None] * n
        try:
            for i in range(n):
                cache.set_end(i)
                v = _eval_numeric(
                    expr,
                    db=db,
                    settings=settings,
                    cache=cache,  # type: ignore[arg-type]
                    holding=None,
                    params={},
                    custom_indicators=custom_indicators,
                    allow_fetch=False,
                )
                values[i] = float(v.now) if v.now is not None else None
        except Exception as exc:
            errors[display] = str(exc)
        out[display] = values

    return SymbolIndicatorsResponse(
        symbol=sym,
        exchange=exch,
        start=start,
        end=end,
        ts=ts,
        series=out,
        errors=errors,
    )


class SignalMarker(BaseModel):
    ts: str
    kind: str  # TRUE/CROSSOVER/CROSSUNDER
    text: Optional[str] = None


class SymbolSignalsRequest(BaseModel):
    symbol: str
    exchange: str = "NSE"
    range: str = "6m"
    timeframe: str = "1d"
    hydrate_mode: str = "auto"  # none|auto|force
    variables: List[AlertVariableDef] = []
    condition_dsl: str


class SymbolSignalsResponse(BaseModel):
    symbol: str
    exchange: str
    start: datetime
    end: datetime
    markers: List[SignalMarker] = []
    errors: List[str] = []


@router.post("/symbol-signals", response_model=SymbolSignalsResponse)
def symbol_signals(
    payload: SymbolSignalsRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_current_user_optional),
) -> SymbolSignalsResponse:
    """Evaluate a DSL condition historically and return chart markers."""

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    sym, exch = _normalize_symbol_exchange(payload.symbol, payload.exchange)
    now = _now_ist_naive()
    start, end = _clamp_range(now, payload.range)

    hydrate_mode = (payload.hydrate_mode or "auto").strip().lower()
    tf = (payload.timeframe or "1d").strip().lower()
    if tf != "1d":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only 1d timeframe is supported for symbol signals (currently).",
        )

    if hydrate_mode == "force":
        ensure_history_window(
            db,
            settings,
            symbol=sym,
            exchange=exch,
            base_timeframe=tf,
            start=start,
            end=end,
        )
    elif hydrate_mode == "auto":
        try:
            ensure_history(
                db,
                settings,
                symbol=sym,
                exchange=exch,
                base_timeframe=tf,
                start=start,
                end=end,
            )
        except Exception:
            pass

    candles = load_series(
        db,
        settings,
        symbol=sym,
        exchange=exch,
        timeframe="1d",  # type: ignore[arg-type]
        start=start,
        end=end,
        allow_fetch=False,
    )
    if not candles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No candles found for this symbol in the requested window.",
        )

    custom_indicators = compile_custom_indicators_for_user(
        db, user_id=user.id, dsl_profile=settings.dsl_profile
    )
    raw_vars = [_model_dump(v) for v in (payload.variables or [])]
    cond_ast, _cadence, _var_map = compile_alert_expression_parts(
        db,
        user_id=user.id,
        variables=raw_vars,
        condition_dsl=payload.condition_dsl,
        evaluation_cadence="1d",
        custom_indicators=custom_indicators,
        dsl_profile=settings.dsl_profile,
    )

    cache = _InMemoryCandleCache(symbol=sym, exchange=exch, candles=candles)

    root_kind: str | None = None
    if isinstance(cond_ast, CallNode) and cond_ast.name.upper() in {
        "CROSSOVER",
        "CROSSUNDER",
        "CROSSING_ABOVE",
        "CROSSING_BELOW",
    }:
        name = cond_ast.name.upper()
        if name == "CROSSING_ABOVE":
            root_kind = "CROSSOVER"
        elif name == "CROSSING_BELOW":
            root_kind = "CROSSUNDER"
        else:
            root_kind = name
    if isinstance(cond_ast, EventNode):
        op = _EVENT_ALIASES.get(cond_ast.op.upper(), cond_ast.op.upper())
        if op == "CROSSES_ABOVE":
            root_kind = "CROSSOVER"
        elif op == "CROSSES_BELOW":
            root_kind = "CROSSUNDER"

    markers: list[SignalMarker] = []
    errors: list[str] = []

    def _bool(n: ExprNode) -> bool:
        if isinstance(n, LogicalNode):
            op = n.op.upper()
            if op == "AND":
                return all(_bool(c) for c in n.children)
            if op == "OR":
                return any(_bool(c) for c in n.children)
            raise ValueError(f"Unknown logical op '{n.op}'")
        if isinstance(n, NotNode):
            return not _bool(n.child)
        if isinstance(n, ComparisonNode):
            left = _eval_numeric(
                n.left,
                db=db,
                settings=settings,
                cache=cache,  # type: ignore[arg-type]
                holding=None,
                params={},
                custom_indicators=custom_indicators,
                allow_fetch=False,
            )
            right = _eval_numeric(
                n.right,
                db=db,
                settings=settings,
                cache=cache,  # type: ignore[arg-type]
                holding=None,
                params={},
                custom_indicators=custom_indicators,
                allow_fetch=False,
            )
            if left.now is None or right.now is None:
                return False
            op = n.op
            if op == "GT":
                return left.now > right.now
            if op == "GTE":
                return left.now >= right.now
            if op == "LT":
                return left.now < right.now
            if op == "LTE":
                return left.now <= right.now
            if op == "EQ":
                return left.now == right.now
            if op == "NEQ":
                return left.now != right.now
            raise ValueError(f"Unknown comparison op '{op}'")
        if isinstance(n, EventNode):
            op = _EVENT_ALIASES.get(n.op.upper(), n.op.upper())
            left = _eval_numeric(
                n.left,
                db=db,
                settings=settings,
                cache=cache,  # type: ignore[arg-type]
                holding=None,
                params={},
                custom_indicators=custom_indicators,
                allow_fetch=False,
            )
            right = _eval_numeric(
                n.right,
                db=db,
                settings=settings,
                cache=cache,  # type: ignore[arg-type]
                holding=None,
                params={},
                custom_indicators=custom_indicators,
                allow_fetch=False,
            )
            if op in {"CROSSES_ABOVE", "CROSSES_BELOW"}:
                if left.prev is None or left.now is None:
                    return False
                if isinstance(n.right, NumberNode):
                    level = float(n.right.value)
                    if op == "CROSSES_ABOVE":
                        return left.prev <= level < left.now
                    return left.prev >= level > left.now
                if right.prev is None or right.now is None:
                    return False
                if op == "CROSSES_ABOVE":
                    return left.prev <= right.prev and left.now > right.now
                return left.prev >= right.prev and left.now < right.now

            if op in {"MOVING_UP", "MOVING_DOWN"}:
                if left.prev is None or left.now is None:
                    return False
                if right.now is None or left.prev == 0:
                    return False
                change_pct = (left.now - left.prev) / abs(left.prev) * 100.0
                threshold = float(right.now)
                if op == "MOVING_UP":
                    return change_pct >= threshold
                return (-change_pct) >= threshold

            raise ValueError(f"Unknown event op '{n.op}'")

        # Numeric root: treat non-zero as True.
        numeric = _eval_numeric(
            n,
            db=db,
            settings=settings,
            cache=cache,  # type: ignore[arg-type]
            holding=None,
            params={},
            custom_indicators=custom_indicators,
            allow_fetch=False,
        )
        return bool(numeric.now)

    ts_list = [c["ts"].date().isoformat() for c in candles if c.get("ts")]
    n = len(ts_list)
    prev_ok = False
    for i in range(n):
        cache.set_end(i)
        try:
            ok = _bool(cond_ast)
        except Exception as exc:
            errors.append(str(exc))
            break
        if root_kind:
            # CROSS* operators are event-like and should be true only on the
            # crossover bar.
            if ok:
                markers.append(SignalMarker(ts=ts_list[i], kind=root_kind))
        else:
            # For generic boolean signals, emit markers only on transitions
            # (false -> true).
            if ok and not prev_ok:
                markers.append(SignalMarker(ts=ts_list[i], kind="TRUE"))
        prev_ok = ok

    return SymbolSignalsResponse(
        symbol=sym,
        exchange=exch,
        start=start,
        end=end,
        markers=markers,
        errors=errors[:10],
    )


@router.post("/symbol-series", response_model=SymbolSeriesResponse)
def symbol_series(
    payload: SymbolSeriesRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_current_user_optional),
) -> SymbolSeriesResponse:
    """Return daily candles for a symbol and optionally hydrate missing data.

    Hydration policy:
    - `auto`: silently hydrate small tail gaps (last 30–60 days).
    - `force`: hydrate the entire requested window (explicit user action).
    - `none`: never fetch (local DB only).
    """

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    sym = (payload.symbol or "").strip().upper()
    sym, exch = _normalize_symbol_exchange(sym, payload.exchange)
    tf = (payload.timeframe or "1d").strip().lower()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol is required.")
    if tf != "1d":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only 1d timeframe is supported for Symbol Explorer (currently).",
        )

    now = _now_ist_naive()
    start, end = _clamp_range(now, payload.range)
    requested_days = _gap_days(start, end)
    big_gap_days = _big_gap_threshold_days(requested_days)

    # Inspect local coverage first.
    local_min: datetime | None = (
        db.query(func.min(Candle.ts))
        .filter(
            Candle.symbol == sym,
            Candle.exchange == exch,
            Candle.timeframe == tf,
            and_(Candle.ts >= start, Candle.ts <= end),
        )
        .scalar()
    )
    local_max: datetime | None = (
        db.query(func.max(Candle.ts))
        .filter(
            Candle.symbol == sym,
            Candle.exchange == exch,
            Candle.timeframe == tf,
            and_(Candle.ts >= start, Candle.ts <= end),
        )
        .scalar()
    )

    head_gap = _gap_days(start, local_min) if local_min is not None else requested_days
    tail_gap = _gap_days(local_max, end) if local_max is not None else requested_days

    hydrate_mode = (payload.hydrate_mode or "auto").strip().lower()
    did_hydrate = False
    if hydrate_mode == "force":
        ensure_history_window(
            db,
            settings,
            symbol=sym,
            exchange=exch,
            base_timeframe=tf,
            start=start,
            end=end,
        )
        did_hydrate = True
    elif hydrate_mode == "auto":
        # Single-symbol explorer: it's acceptable to hydrate the requested window
        # automatically (bounded by MAX_HISTORY_YEARS) so the chart "just works",
        # even when the symbol isn't in holdings.
        try:
            ensure_history(
                db,
                settings,
                symbol=sym,
                exchange=exch,
                base_timeframe=tf,
                start=start,
                end=end,
            )
            did_hydrate = True
        except Exception:
            did_hydrate = False
        if not did_hydrate:
            # Best-effort tail fill (may still succeed even if the full window didn't).
            try:
                did_hydrate = _maybe_hydrate_tail_gap(
                    db,
                    settings,
                    symbol=sym,
                    exchange=exch,
                    timeframe=tf,
                    start=start,
                    end=end,
                    max_days=60,
                )
            except Exception:
                did_hydrate = False

    if did_hydrate:
        local_min = (
            db.query(func.min(Candle.ts))
            .filter(
                Candle.symbol == sym,
                Candle.exchange == exch,
                Candle.timeframe == tf,
                and_(Candle.ts >= start, Candle.ts <= end),
            )
            .scalar()
        )
        local_max = (
            db.query(func.max(Candle.ts))
            .filter(
                Candle.symbol == sym,
                Candle.exchange == exch,
                Candle.timeframe == tf,
                and_(Candle.ts >= start, Candle.ts <= end),
            )
            .scalar()
        )
        head_gap = (
            _gap_days(start, local_min) if local_min is not None else requested_days
        )
        tail_gap = (
            _gap_days(local_max, end) if local_max is not None else requested_days
        )

    candles = load_series(
        db,
        settings,
        symbol=sym,
        exchange=exch,
        timeframe="1d",  # type: ignore[arg-type]
        start=start,
        end=end,
        allow_fetch=False,
    )

    needs_hydrate_history = False
    if not candles:
        needs_hydrate_history = True
    elif local_min is not None and head_gap > big_gap_days:
        global_min = (
            db.query(func.min(Candle.ts))
            .filter(
                Candle.symbol == sym,
                Candle.exchange == exch,
                Candle.timeframe == tf,
            )
            .scalar()
        )
        if global_min is None:
            needs_hydrate_history = True
        else:
            # Late entrant / limited-history: earliest known candle is itself late.
            needs_hydrate_history = global_min <= start + timedelta(days=big_gap_days)

    return SymbolSeriesResponse(
        symbol=sym,
        exchange=exch,
        start=start,
        end=end,
        points=[
            SymbolSeriesPoint(
                ts=c["ts"].date().isoformat(),
                open=float(c["open"]),
                high=float(c["high"]),
                low=float(c["low"]),
                close=float(c["close"]),
                volume=float(c.get("volume") or 0.0),
            )
            for c in candles
            if c.get("ts")
        ],
        local_first=local_min,
        local_last=local_max,
        head_gap_days=int(head_gap),
        tail_gap_days=int(tail_gap),
        needs_hydrate_history=needs_hydrate_history,
    )


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

    included_count = len(returns_by_symbol)
    if included_count < 2 or not date_sets:
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
    # edges in an undirected graph and compute connected components. When
    # the graph collapses into a single component, we later add a simple
    # two-cluster split to reveal A/B-style groups.
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

    # If everything ends up in a single graph component but there are at
    # least a few symbols, derive a light-weight two-way split based on
    # similarity to two “centres” so that the analytics view can still
    # show A/B-style clusters.
    if len(raw_clusters) == 1 and len(symbol_list) >= 3:
        members = raw_clusters[0]
        idxs = [idx_by_symbol[sym] for sym in members]

        def _sim(i: int, j: int) -> float:
            val = matrix[i][j]
            if val is None or val < 0:
                return 0.0
            return float(val)

        # First centre: symbol with highest average positive similarity.
        centre1: int = idxs[0]
        best_avg = -1.0
        for i in idxs:
            vals = [_sim(i, j) for j in idxs if j != i]
            if not vals:
                continue
            avg = sum(vals) / len(vals)
            if avg > best_avg:
                best_avg = avg
                centre1 = i

        # Second centre: symbol least similar to centre1.
        centre2: int = idxs[0]
        worst_sim = 2.0
        for j in idxs:
            if j == centre1:
                continue
            s_val = _sim(centre1, j)
            if s_val < worst_sim:
                worst_sim = s_val
                centre2 = j

        cluster_a: List[str] = []
        cluster_b: List[str] = []
        for i in idxs:
            s1 = _sim(i, centre1)
            s2 = _sim(i, centre2)
            if s1 >= s2:
                cluster_a.append(symbol_list[i])
            else:
                cluster_b.append(symbol_list[i])

        if cluster_a and cluster_b:
            raw_clusters = [cluster_a, cluster_b]

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

        weight = weights_used.get(sym)
        role: Optional[str] = None
        if avg_for_sym is not None and weight is not None:
            if weight >= 0.04 and avg_for_sym >= 0.4:
                role = "core-driver"
            elif avg_for_sym <= 0.1:
                role = "diversifier"
            else:
                role = "satellite"

        symbol_stats.append(
            SymbolCorrelationStats(
                symbol=sym,
                average_correlation=avg_for_sym,
                most_correlated_symbol=most_sym,
                most_correlated_value=most_val,
                cluster=cluster_label_by_symbol.get(sym),
                weight_fraction=weights_used.get(sym),
                role=role,
            ),
        )

    # Simple notion of “effective independent bets” based on cluster
    # weights: 1 / sum(w_i^2) where w_i are cluster weights.
    effective_independent_bets: Optional[float] = None
    cluster_weights = [c.weight_fraction or 0.0 for c in cluster_summaries]
    denom = sum(w * w for w in cluster_weights if w > 0)
    if denom > 0:
        effective_independent_bets = 1.0 / denom

    # Add robustness hints: very small sample sizes and excluded holdings
    # make correlation-driven insights more tentative.
    if observations < 20:
        recommendations.append(
            (
                "Correlation estimates are based on a limited number of "
                "observations; treat diversification insights as tentative."
            ),
        )

    excluded_count = max(0, len(symbol_values) - len(symbol_list))
    if excluded_count > 0:
        recommendations.append(
            (
                f"{excluded_count} holding(s) were excluded due to missing or "
                "insufficient price history; only the symbols shown below are "
                "included in this analysis."
            ),
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
        symbol_stats=symbol_stats,
        clusters=cluster_summaries,
        effective_independent_bets=effective_independent_bets,
    )


__all__ = ["router"]
