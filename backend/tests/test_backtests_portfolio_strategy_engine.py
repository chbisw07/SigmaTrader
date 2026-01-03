from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.schemas.backtests_portfolio_strategy import PortfolioStrategyBacktestConfigIn
from app.services import backtests_portfolio_strategy as ps
from app.services.backtests_data import UniverseSymbolRef


def _bars_5m(d: date, n: int = 8, *, px: float = 100.0) -> list[dict]:
    start = datetime.combine(d, time(9, 15))
    out: list[dict] = []
    for i in range(n):
        ts = start + timedelta(minutes=5 * i)
        out.append(
            {
                "ts": ts,
                "open": px,
                "high": px,
                "low": px,
                "close": px,
                "volume": 1000.0,
            }
        )
    return out


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


def test_portfolio_strategy_cooldown_bars_delays_reentry(monkeypatch) -> None:
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    get_settings.cache_clear()

    d = date(2025, 1, 2)
    bars = _bars_5m(d, 8, px=100.0)

    def _stub_load_series(*_args, symbol: str, exchange: str, **_kwargs) -> list[dict]:
        assert exchange == "NSE"
        assert symbol == "AAA"
        return bars

    monkeypatch.setattr(ps, "load_series", _stub_load_series)

    cfg = PortfolioStrategyBacktestConfigIn(
        timeframe="5m",
        start_date=d,
        end_date=d,
        entry_dsl="PRICE() > 0",
        exit_dsl="PRICE() > 0",
        product="CNC",
        direction="LONG",
        initial_cash=10000.0,
        max_open_positions=1,
        allocation_mode="EQUAL",
        sizing_mode="CASH_PER_SLOT",
        cooldown_bars=1,
        charges_model="BPS",
        charges_bps=0.0,
        include_dp_charges=False,
    )

    with SessionLocal() as db:
        res = ps.run_portfolio_strategy_backtest(
            db,
            get_settings(),
            symbols=[UniverseSymbolRef(exchange="NSE", symbol="AAA")],
            config=cfg,
            allow_fetch=False,
        )

    trades = res["trades"]
    assert len(trades) == 2
    assert {t["reason"] for t in trades} == {"EXIT_SIGNAL"}

    # Trade 1: entry at bar1, exit at bar2; Trade 2: entry at bar5, exit at bar6.
    t1 = trades[0]
    t2 = trades[1]
    assert _parse_iso(t1["entry_ts"]).time() == time(9, 20)
    assert _parse_iso(t1["exit_ts"]).time() == time(9, 25)
    assert _parse_iso(t2["entry_ts"]).time() == time(9, 40)
    assert _parse_iso(t2["exit_ts"]).time() == time(9, 45)


def test_portfolio_strategy_min_holding_bars_blocks_early_exit(monkeypatch) -> None:
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    get_settings.cache_clear()

    d = date(2025, 1, 2)
    bars = _bars_5m(d, 8, px=100.0)

    def _stub_load_series(*_args, symbol: str, exchange: str, **_kwargs) -> list[dict]:
        assert exchange == "NSE"
        assert symbol == "AAA"
        return bars

    monkeypatch.setattr(ps, "load_series", _stub_load_series)

    cfg = PortfolioStrategyBacktestConfigIn(
        timeframe="5m",
        start_date=d,
        end_date=d,
        entry_dsl="PRICE() > 0",
        exit_dsl="PRICE() > 0",
        product="CNC",
        direction="LONG",
        initial_cash=10000.0,
        max_open_positions=1,
        allocation_mode="EQUAL",
        sizing_mode="CASH_PER_SLOT",
        min_holding_bars=2,
        charges_model="BPS",
        charges_bps=0.0,
        include_dp_charges=False,
    )

    with SessionLocal() as db:
        res = ps.run_portfolio_strategy_backtest(
            db,
            get_settings(),
            symbols=[UniverseSymbolRef(exchange="NSE", symbol="AAA")],
            config=cfg,
            allow_fetch=False,
        )

    trades = res["trades"]
    assert len(trades) == 1
    tr = trades[0]
    assert _parse_iso(tr["entry_ts"]).time() == time(9, 20)
    assert _parse_iso(tr["exit_ts"]).time() == time(9, 35)
