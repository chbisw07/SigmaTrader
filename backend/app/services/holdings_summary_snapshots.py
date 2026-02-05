from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Iterable

from sqlalchemy import func, tuple_
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.market_hours import IST_OFFSET
from app.models import Candle, HoldingsSummarySnapshot
from app.schemas.positions import HoldingRead
from app.services.market_data import load_series

DEFAULT_ALPHA_BETA_BENCHMARK = ("NSE", "NIFTYBEES")
DEFAULT_RISK_FREE_RATE_PCT = 6.5


def _as_of_date_ist(now_utc: datetime) -> date:
    try:
        from zoneinfo import ZoneInfo

        return now_utc.astimezone(ZoneInfo("Asia/Kolkata")).date()
    except Exception:
        return now_utc.date()


def _now_ist_naive() -> datetime:
    return (datetime.now(UTC) + IST_OFFSET).replace(tzinfo=None)


def _to_date_key(dt: datetime) -> str:
    return dt.date().isoformat()


@dataclass(frozen=True)
class HoldingsSummaryMetrics:
    holdings_count: int
    funds_available: float | None
    invested: float | None
    equity_value: float | None
    account_value: float | None

    total_pnl_pct: float | None
    today_pnl_pct: float | None
    overall_win_rate: float | None
    today_win_rate: float | None

    alpha_annual_pct: float | None
    beta: float | None

    cagr_1y_pct: float | None
    cagr_2y_pct: float | None
    cagr_1y_coverage_pct: float | None
    cagr_2y_coverage_pct: float | None

    benchmark_exchange: str | None
    benchmark_symbol: str | None
    risk_free_rate_pct: float | None


def _safe_float(v: object) -> float | None:
    try:
        f = float(v)  # type: ignore[arg-type]
    except Exception:
        return None
    return f if f is not None and f == f else None  # noqa: PLR0124


def compute_holdings_summary_metrics(
    *,
    holdings: Iterable[HoldingRead],
    funds_available: float | None,
    settings: Settings,
    db: Session,
    allow_fetch_market_data: bool = False,
    benchmark: tuple[str, str] = DEFAULT_ALPHA_BETA_BENCHMARK,
    risk_free_rate_pct: float = DEFAULT_RISK_FREE_RATE_PCT,
) -> HoldingsSummaryMetrics:
    active_rows: list[HoldingRead] = []
    for row in holdings:
        symbol = str(getattr(row, "symbol", "") or "").strip()
        if not symbol:
            continue
        qty = _safe_float(getattr(row, "quantity", None)) or 0.0
        if qty > 0:
            active_rows.append(row)

    invested = 0.0
    equity_value = 0.0
    today_weighted_return = 0.0
    today_return_weight = 0.0

    overall_winner = 0
    overall_comparable = 0
    today_winner = 0
    today_comparable = 0

    for row in active_rows:
        qty = _safe_float(getattr(row, "quantity", None)) or 0.0
        avg_price = _safe_float(getattr(row, "average_price", None)) or 0.0
        last_price = _safe_float(getattr(row, "last_price", None))

        invested_value = qty * avg_price if qty > 0 and avg_price > 0 else 0.0
        current = qty * last_price if qty > 0 and (last_price or 0) > 0 else invested_value

        invested += invested_value
        equity_value += current

        total_pnl_pct_row = _safe_float(getattr(row, "total_pnl_percent", None))
        if total_pnl_pct_row is not None:
            overall_comparable += 1
            if total_pnl_pct_row > 0:
                overall_winner += 1

        today_pnl_pct_row = _safe_float(getattr(row, "today_pnl_percent", None))
        if today_pnl_pct_row is not None:
            today_comparable += 1
            if today_pnl_pct_row > 0:
                today_winner += 1
            if current > 0:
                today_weighted_return += (today_pnl_pct_row / 100.0) * current
                today_return_weight += current

    holdings_count = len(active_rows)
    total_pnl_pct = ((equity_value - invested) / invested) * 100.0 if invested > 0 else None
    today_pnl_pct = (today_weighted_return / today_return_weight) * 100.0 if today_return_weight > 0 else None
    overall_win_rate = (overall_winner / overall_comparable) * 100.0 if overall_comparable > 0 else None
    today_win_rate = (today_winner / today_comparable) * 100.0 if today_comparable > 0 else None

    account_value = None
    if funds_available is not None and funds_available == funds_available:
        account_value = float(funds_available) + float(equity_value)

    alpha_annual_pct, beta = _compute_alpha_beta(
        db=db,
        settings=settings,
        active_rows=active_rows,
        allow_fetch_market_data=allow_fetch_market_data,
        benchmark=benchmark,
        risk_free_rate_pct=risk_free_rate_pct,
    )

    cagr_1y_pct, cagr_1y_cov = _compute_portfolio_cagr(
        db=db,
        settings=settings,
        active_rows=active_rows,
        trading_days=252,
        allow_fetch_market_data=allow_fetch_market_data,
        equity_value=equity_value,
    )
    cagr_2y_pct, cagr_2y_cov = _compute_portfolio_cagr(
        db=db,
        settings=settings,
        active_rows=active_rows,
        trading_days=504,
        allow_fetch_market_data=allow_fetch_market_data,
        equity_value=equity_value,
    )

    bench_exch, bench_sym = benchmark
    return HoldingsSummaryMetrics(
        holdings_count=holdings_count,
        funds_available=float(funds_available) if funds_available is not None else None,
        invested=float(invested) if invested or invested == 0 else None,
        equity_value=float(equity_value) if equity_value or equity_value == 0 else None,
        account_value=account_value,
        total_pnl_pct=total_pnl_pct,
        today_pnl_pct=today_pnl_pct,
        overall_win_rate=overall_win_rate,
        today_win_rate=today_win_rate,
        alpha_annual_pct=alpha_annual_pct,
        beta=beta,
        cagr_1y_pct=cagr_1y_pct,
        cagr_2y_pct=cagr_2y_pct,
        cagr_1y_coverage_pct=cagr_1y_cov,
        cagr_2y_coverage_pct=cagr_2y_cov,
        benchmark_exchange=bench_exch,
        benchmark_symbol=bench_sym,
        risk_free_rate_pct=float(risk_free_rate_pct) if risk_free_rate_pct is not None else None,
    )


def upsert_holdings_summary_snapshot(
    db: Session,
    *,
    user_id: int,
    broker_name: str,
    as_of_date: date,
    metrics: HoldingsSummaryMetrics,
) -> HoldingsSummarySnapshot:
    broker = (broker_name or "").strip().lower() or "zerodha"
    row: HoldingsSummarySnapshot | None = (
        db.query(HoldingsSummarySnapshot)
        .filter(
            HoldingsSummarySnapshot.user_id == int(user_id),
            HoldingsSummarySnapshot.broker_name == broker,
            HoldingsSummarySnapshot.as_of_date == as_of_date,
        )
        .one_or_none()
    )
    if row is None:
        row = HoldingsSummarySnapshot(
            user_id=int(user_id),
            broker_name=broker,
            as_of_date=as_of_date,
        )

    row.captured_at = datetime.now(UTC)
    row.holdings_count = int(metrics.holdings_count)
    row.funds_available = metrics.funds_available
    row.invested = metrics.invested
    row.equity_value = metrics.equity_value
    row.account_value = metrics.account_value
    row.total_pnl_pct = metrics.total_pnl_pct
    row.today_pnl_pct = metrics.today_pnl_pct
    row.overall_win_rate = metrics.overall_win_rate
    row.today_win_rate = metrics.today_win_rate
    row.alpha_annual_pct = metrics.alpha_annual_pct
    row.beta = metrics.beta
    row.cagr_1y_pct = metrics.cagr_1y_pct
    row.cagr_2y_pct = metrics.cagr_2y_pct
    row.cagr_1y_coverage_pct = metrics.cagr_1y_coverage_pct
    row.cagr_2y_coverage_pct = metrics.cagr_2y_coverage_pct
    row.benchmark_exchange = metrics.benchmark_exchange
    row.benchmark_symbol = metrics.benchmark_symbol
    row.risk_free_rate_pct = metrics.risk_free_rate_pct

    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _load_daily_history_points(
    db: Session,
    settings: Settings,
    *,
    exchange: str,
    symbol: str,
    start: datetime,
    end: datetime,
    allow_fetch_market_data: bool,
) -> list[dict]:
    return load_series(
        db,
        settings,
        symbol=symbol,
        exchange=exchange,
        timeframe="1d",
        start=start,
        end=end,
        allow_fetch=allow_fetch_market_data,
    )


def _compute_portfolio_cagr(
    *,
    db: Session,
    settings: Settings,
    active_rows: list[HoldingRead],
    trading_days: int,
    allow_fetch_market_data: bool,
    equity_value: float,
) -> tuple[float | None, float | None]:
    if trading_days <= 0:
        return None, None

    now = _now_ist_naive()
    start = now - timedelta(days=365 * 2 + 15)
    end = now

    start_value = 0.0
    end_value = 0.0
    covered_current_value = 0.0

    for row in active_rows:
        sym = str(getattr(row, "symbol", "") or "").strip().upper()
        exch = str(getattr(row, "exchange", "") or "NSE").strip().upper() or "NSE"
        qty = _safe_float(getattr(row, "quantity", None)) or 0.0
        if qty <= 0:
            continue

        history = _load_daily_history_points(
            db,
            settings,
            exchange=exch,
            symbol=sym,
            start=start,
            end=end,
            allow_fetch_market_data=allow_fetch_market_data,
        )
        end_close = None
        if history:
            end_close = _safe_float(history[-1].get("close"))
        if end_close is None:
            end_close = _safe_float(getattr(row, "last_price", None))
        if end_close is None or end_close <= 0:
            continue

        covered_current_value += qty * end_close

        start_index = len(history) - (trading_days + 1)
        if start_index < 0 or start_index >= len(history):
            continue
        start_close = _safe_float(history[start_index].get("close"))
        if start_close is None or start_close <= 0:
            continue

        start_value += qty * start_close
        end_value += qty * end_close

    coverage_pct = (
        (covered_current_value / equity_value) * 100.0
        if equity_value > 0 and covered_current_value > 0
        else None
    )
    if start_value <= 0 or end_value <= 0:
        return None, coverage_pct

    exponent = 252.0 / float(trading_days)
    ratio = end_value / start_value
    if exponent <= 0 or ratio <= 0:
        return None, coverage_pct

    cagr_pct = (pow(ratio, exponent) - 1.0) * 100.0
    return (cagr_pct if cagr_pct == cagr_pct else None), coverage_pct  # noqa: PLR0124


def _compute_alpha_beta(
    *,
    db: Session,
    settings: Settings,
    active_rows: list[HoldingRead],
    allow_fetch_market_data: bool,
    benchmark: tuple[str, str],
    risk_free_rate_pct: float,
) -> tuple[float | None, float | None]:
    bench_exch, bench_sym = benchmark
    now = _now_ist_naive()
    start = now - timedelta(days=365 * 2 + 15)
    end = now

    bench_history = _load_daily_history_points(
        db,
        settings,
        exchange=str(bench_exch).upper(),
        symbol=str(bench_sym).upper(),
        start=start,
        end=end,
        allow_fetch_market_data=allow_fetch_market_data,
    )
    if len(bench_history) < 200 or not active_rows:
        return None, None

    rf_annual = float(risk_free_rate_pct) if risk_free_rate_pct is not None else DEFAULT_RISK_FREE_RATE_PCT
    if rf_annual < 0 or rf_annual > 100:
        rf_annual = DEFAULT_RISK_FREE_RATE_PCT
    daily_rf = pow(1.0 + rf_annual / 100.0, 1.0 / 252.0) - 1.0

    bench_by_date: dict[str, float] = {}
    for p in bench_history:
        ts = p.get("ts")
        close = _safe_float(p.get("close"))
        if not isinstance(ts, datetime) or close is None or close <= 0:
            continue
        bench_by_date[_to_date_key(ts)] = close

    bench_dates = sorted(bench_by_date.keys())
    if len(bench_dates) < 160:
        return None, None

    window_days = 126
    dates = bench_dates[-(window_days + 1) :]

    quantities: dict[str, float] = {}
    exchanges: dict[str, str] = {}
    for row in active_rows:
        sym = str(getattr(row, "symbol", "") or "").strip().upper()
        exch = str(getattr(row, "exchange", "") or "NSE").strip().upper() or "NSE"
        qty = _safe_float(getattr(row, "quantity", None)) or 0.0
        if sym and qty > 0:
            quantities[sym] = qty
            exchanges[sym] = exch

    close_by_symbol: dict[str, dict[str, float]] = {}
    # Bulk-load candles for held symbols when possible to keep this fast.
    pairs = [(exchanges[s], s) for s in quantities.keys() if s in exchanges]
    if pairs:
        candles = (
            db.query(Candle)
            .filter(
                Candle.timeframe == "1d",
                tuple_(Candle.exchange, Candle.symbol).in_(pairs),
                func.date(Candle.ts) >= start.date(),
                func.date(Candle.ts) <= end.date(),
            )
            .order_by(Candle.exchange, Candle.symbol, Candle.ts)
            .all()
        )
        for c in candles:
            key = c.symbol.upper()
            by_date = close_by_symbol.setdefault(key, {})
            by_date[_to_date_key(c.ts)] = float(c.close)

    # Fallback: if candle store is empty, try per-symbol load_series (may fetch if enabled).
    for sym, _qty in quantities.items():
        if sym in close_by_symbol and len(close_by_symbol[sym]) >= 160:
            continue
        exch = exchanges.get(sym, "NSE")
        hist = _load_daily_history_points(
            db,
            settings,
            exchange=exch,
            symbol=sym,
            start=start,
            end=end,
            allow_fetch_market_data=allow_fetch_market_data,
        )
        by_date: dict[str, float] = {}
        for p in hist:
            ts = p.get("ts")
            close = _safe_float(p.get("close"))
            if not isinstance(ts, datetime) or close is None or close <= 0:
                continue
            by_date[_to_date_key(ts)] = close
        if len(by_date) >= 160:
            close_by_symbol[sym] = by_date

    portfolio_series: list[float] = []
    benchmark_series: list[float] = []
    for d in dates:
        bench_close = bench_by_date.get(d)
        if bench_close is None:
            continue
        portfolio_value_at_date = 0.0
        for sym, qty in quantities.items():
            by_date = close_by_symbol.get(sym)
            if not by_date:
                continue
            close = by_date.get(d)
            if close is None:
                continue
            portfolio_value_at_date += qty * close
        if portfolio_value_at_date > 0:
            portfolio_series.append(portfolio_value_at_date)
            benchmark_series.append(bench_close)

    if len(portfolio_series) < 80:
        return None, None

    port_excess: list[float] = []
    bench_excess: list[float] = []
    for i in range(1, len(portfolio_series)):
        prev_p = portfolio_series[i - 1]
        curr_p = portfolio_series[i]
        prev_m = benchmark_series[i - 1]
        curr_m = benchmark_series[i]
        if prev_p <= 0 or curr_p <= 0 or prev_m <= 0 or curr_m <= 0:
            continue
        rp = curr_p / prev_p - 1.0
        rm = curr_m / prev_m - 1.0
        if rp == rp and rm == rm:  # noqa: PLR0124
            port_excess.append(rp - daily_rf)
            bench_excess.append(rm - daily_rf)

    if len(port_excess) < 60:
        return None, None

    mean_p = sum(port_excess) / len(port_excess)
    mean_m = sum(bench_excess) / len(bench_excess)

    cov = 0.0
    var_m = 0.0
    for dp, dm in zip(port_excess, bench_excess, strict=False):
        ap = dp - mean_p
        am = dm - mean_m
        cov += ap * am
        var_m += am * am

    denom = max(len(port_excess) - 1, 1)
    cov /= denom
    var_m /= denom
    if var_m <= 0:
        return None, None

    beta = cov / var_m
    if beta != beta:  # noqa: PLR0124
        return None, None

    alpha_daily = mean_p - beta * mean_m
    alpha_annual_pct = alpha_daily * 252.0 * 100.0
    return (
        alpha_annual_pct if alpha_annual_pct == alpha_annual_pct else None,  # noqa: PLR0124
        beta,
    )


__all__ = [
    "DEFAULT_ALPHA_BETA_BENCHMARK",
    "DEFAULT_RISK_FREE_RATE_PCT",
    "HoldingsSummaryMetrics",
    "compute_holdings_summary_metrics",
    "upsert_holdings_summary_snapshot",
    "_as_of_date_ist",
]
