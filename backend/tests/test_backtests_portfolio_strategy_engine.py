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


def _bars_5m_closes(d: date, closes: list[float]) -> list[dict]:
    start = datetime.combine(d, time(9, 15))
    out: list[dict] = []
    prev_close = closes[0]
    for i, close_px in enumerate(closes):
        ts = start + timedelta(minutes=5 * i)
        open_px = prev_close if i > 0 else close_px
        out.append(
            {
                "ts": ts,
                "open": float(open_px),
                "high": float(max(open_px, close_px)),
                "low": float(min(open_px, close_px)),
                "close": float(close_px),
                "volume": 1000.0,
            }
        )
        prev_close = close_px
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


def test_portfolio_strategy_trailing_activation_allows_breakeven_exit(
    monkeypatch,
) -> None:
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    get_settings.cache_clear()

    d = date(2025, 1, 2)
    bars = _bars_5m_closes(d, [100.0, 100.0, 103.0, 100.0, 100.0])

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
        exit_dsl="PRICE() < 0",
        product="CNC",
        direction="LONG",
        initial_cash=10000.0,
        max_open_positions=1,
        allocation_mode="EQUAL",
        sizing_mode="PCT_EQUITY",
        position_size_pct=100.0,
        stop_loss_pct=0.0,
        take_profit_pct=0.0,
        trailing_stop_pct=3.0,
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
    assert trades[0]["reason"] == "TRAILING_STOP"
    assert abs(float(trades[0]["pnl_pct"])) < 1e-9


def test_portfolio_strategy_trailing_stop_short_symmetry(monkeypatch) -> None:
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    get_settings.cache_clear()

    d = date(2025, 1, 2)
    bars = _bars_5m_closes(d, [100.0, 100.0, 97.0, 100.0, 100.0])

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
        exit_dsl="PRICE() < 0",
        product="MIS",
        direction="SHORT",
        initial_cash=10000.0,
        max_open_positions=1,
        allocation_mode="EQUAL",
        sizing_mode="PCT_EQUITY",
        position_size_pct=100.0,
        stop_loss_pct=0.0,
        take_profit_pct=0.0,
        trailing_stop_pct=3.0,
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
    assert trades[0]["reason"] == "TRAILING_STOP"
    assert abs(float(trades[0]["pnl_pct"])) < 1e-9


def test_portfolio_strategy_reentry_disabled_does_not_change_results(
    monkeypatch,
) -> None:
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    get_settings.cache_clear()

    d = date(2025, 1, 2)
    closes = [100.0, 100.0, 103.0, 105.0, 104.0, 101.8, 101.8, 100.0, 100.0, 100.0]
    bars = _bars_5m_closes(d, closes)

    def _stub_load_series(*_args, symbol: str, exchange: str, **_kwargs) -> list[dict]:
        assert exchange == "NSE"
        assert symbol in {"AAA", "BBB"}
        return bars

    monkeypatch.setattr(ps, "load_series", _stub_load_series)

    cfg_base = PortfolioStrategyBacktestConfigIn(
        timeframe="5m",
        start_date=d,
        end_date=d,
        entry_dsl="PRICE() > 0",
        exit_dsl="PRICE() < 0",
        product="MIS",
        direction="LONG",
        initial_cash=10000.0,
        max_open_positions=2,
        allocation_mode="RANKING",
        ranking_metric="PERF_PCT",
        ranking_window=1,
        sizing_mode="PCT_EQUITY",
        position_size_pct=100.0,
        trailing_stop_pct=3.0,
        charges_model="BPS",
        charges_bps=0.0,
        include_dp_charges=False,
    )
    update = {
        "allow_reentry_after_trailing_stop": False,
        "reentry_cooldown_bars": 3,
        "reentry_rank_gate_enabled": True,
        "reentry_rank_gate_buffer": 2,
    }
    if hasattr(cfg_base, "model_copy"):
        cfg_disabled = cfg_base.model_copy(update=update)  # type: ignore[attr-defined]
    else:  # pragma: no cover - Pydantic v1 fallback
        cfg_disabled = cfg_base.copy(update=update)

    with SessionLocal() as db:
        res_base = ps.run_portfolio_strategy_backtest(
            db,
            get_settings(),
            symbols=[
                UniverseSymbolRef(exchange="NSE", symbol="AAA"),
                UniverseSymbolRef(exchange="NSE", symbol="BBB"),
            ],
            config=cfg_base,
            allow_fetch=False,
        )
        res_disabled = ps.run_portfolio_strategy_backtest(
            db,
            get_settings(),
            symbols=[
                UniverseSymbolRef(exchange="NSE", symbol="AAA"),
                UniverseSymbolRef(exchange="NSE", symbol="BBB"),
            ],
            config=cfg_disabled,
            allow_fetch=False,
        )

    assert res_base["metrics"] == res_disabled["metrics"]
    assert res_base["series"] == res_disabled["series"]
    assert res_base["trades"] == res_disabled["trades"]


def test_portfolio_strategy_reentry_triggers_with_free_slot(monkeypatch) -> None:
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    get_settings.cache_clear()

    d = date(2025, 1, 2)
    aaa_closes = (
        [100.0] * 10 + [103.0, 105.0, 104.0, 101.8, 101.8] + [100.0] * 9 + [120.0] * 6
    )
    bbb_closes = [100.0] * len(aaa_closes)
    bars_by_symbol = {
        "AAA": _bars_5m_closes(d, aaa_closes),
        "BBB": _bars_5m_closes(d, bbb_closes),
    }

    def _stub_load_series(*_args, symbol: str, exchange: str, **_kwargs) -> list[dict]:
        assert exchange == "NSE"
        return bars_by_symbol[symbol]

    monkeypatch.setattr(ps, "load_series", _stub_load_series)

    cfg = PortfolioStrategyBacktestConfigIn(
        timeframe="5m",
        start_date=d,
        end_date=d,
        entry_dsl="PRICE() > 0",
        exit_dsl="PRICE() < 0",
        product="MIS",
        direction="LONG",
        initial_cash=100000.0,
        max_open_positions=2,
        allocation_mode="RANKING",
        ranking_metric="PERF_PCT",
        ranking_window=1,
        sizing_mode="PCT_EQUITY",
        position_size_pct=50.0,
        trailing_stop_pct=3.0,
        cooldown_bars=999,
        allow_reentry_after_trailing_stop=True,
        reentry_cooldown_bars=0,
        reentry_max_per_symbol_per_trend=1,
        reentry_rank_gate_enabled=True,
        reentry_rank_gate_buffer=2,
        reentry_replace_policy="REQUIRE_FREE_SLOT",
        reentry_trend_filter="NONE",
        reentry_trigger="CLOSE_CROSSES_ABOVE_FAST_MA",
        charges_model="BPS",
        charges_bps=0.0,
        include_dp_charges=False,
    )

    with SessionLocal() as db:
        res = ps.run_portfolio_strategy_backtest(
            db,
            get_settings(),
            symbols=[
                UniverseSymbolRef(exchange="NSE", symbol="AAA"),
                UniverseSymbolRef(exchange="NSE", symbol="BBB"),
            ],
            config=cfg,
            allow_fetch=False,
        )

    aaa_trades = [t for t in res["trades"] if t["symbol"] == "NSE:AAA"]
    assert len(aaa_trades) >= 2
    assert aaa_trades[0]["reason"] == "TRAILING_STOP"
    assert aaa_trades[-1]["reason"] == "EOD_SQUARE_OFF"
    assert aaa_trades[-1]["entry_reason"] == "REENTRY_TREND"


def test_portfolio_strategy_reentry_blocked_by_rank_gate(monkeypatch) -> None:
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    get_settings.cache_clear()

    d = date(2025, 1, 2)
    aaa_closes = (
        [100.0] * 10 + [103.0, 105.0, 104.0, 101.8, 101.8] + [100.0] * 9 + [120.0] * 6
    )
    bbb_closes = [100.0] * 24 + [150.0] + [150.0] * (len(aaa_closes) - 25)
    ccc_closes = [100.0] * 24 + [200.0] + [200.0] * (len(aaa_closes) - 25)
    bars_by_symbol = {
        "AAA": _bars_5m_closes(d, aaa_closes),
        "BBB": _bars_5m_closes(d, bbb_closes),
        "CCC": _bars_5m_closes(d, ccc_closes),
    }

    def _stub_load_series(*_args, symbol: str, exchange: str, **_kwargs) -> list[dict]:
        assert exchange == "NSE"
        return bars_by_symbol[symbol]

    monkeypatch.setattr(ps, "load_series", _stub_load_series)

    cfg = PortfolioStrategyBacktestConfigIn(
        timeframe="5m",
        start_date=d,
        end_date=d,
        entry_dsl="PRICE() > 0",
        exit_dsl="PRICE() < 0",
        product="MIS",
        direction="LONG",
        initial_cash=100000.0,
        max_open_positions=2,
        allocation_mode="RANKING",
        ranking_metric="PERF_PCT",
        ranking_window=1,
        sizing_mode="PCT_EQUITY",
        position_size_pct=50.0,
        trailing_stop_pct=3.0,
        cooldown_bars=999,
        allow_reentry_after_trailing_stop=True,
        reentry_cooldown_bars=0,
        reentry_rank_gate_enabled=True,
        reentry_rank_gate_buffer=0,
        reentry_replace_policy="REQUIRE_FREE_SLOT_OR_REPLACE_WORST",
        reentry_trend_filter="NONE",
        charges_model="BPS",
        charges_bps=0.0,
        include_dp_charges=False,
    )

    with SessionLocal() as db:
        res = ps.run_portfolio_strategy_backtest(
            db,
            get_settings(),
            symbols=[
                UniverseSymbolRef(exchange="NSE", symbol="AAA"),
                UniverseSymbolRef(exchange="NSE", symbol="BBB"),
                UniverseSymbolRef(exchange="NSE", symbol="CCC"),
            ],
            config=cfg,
            allow_fetch=False,
        )

    aaa_trades = [t for t in res["trades"] if t["symbol"] == "NSE:AAA"]
    assert len(aaa_trades) == 1
    assert aaa_trades[0]["reason"] == "TRAILING_STOP"


def test_portfolio_strategy_reentry_can_replace_worst_holding(monkeypatch) -> None:
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    get_settings.cache_clear()

    d = date(2025, 1, 2)
    aaa_closes = (
        [100.0] * 10 + [103.0, 105.0, 104.0, 101.8, 101.8] + [100.0] * 9 + [120.0] * 6
    )
    bbb_closes = [100.0] * len(aaa_closes)
    bars_by_symbol = {
        "AAA": _bars_5m_closes(d, aaa_closes),
        "BBB": _bars_5m_closes(d, bbb_closes),
    }

    def _stub_load_series(*_args, symbol: str, exchange: str, **_kwargs) -> list[dict]:
        assert exchange == "NSE"
        return bars_by_symbol[symbol]

    monkeypatch.setattr(ps, "load_series", _stub_load_series)

    cfg = PortfolioStrategyBacktestConfigIn(
        timeframe="5m",
        start_date=d,
        end_date=d,
        entry_dsl="PRICE() > 0",
        exit_dsl="PRICE() < 0",
        product="MIS",
        direction="LONG",
        initial_cash=100000.0,
        max_open_positions=1,
        allocation_mode="RANKING",
        ranking_metric="PERF_PCT",
        ranking_window=1,
        sizing_mode="PCT_EQUITY",
        position_size_pct=100.0,
        trailing_stop_pct=3.0,
        cooldown_bars=1,
        allow_reentry_after_trailing_stop=True,
        reentry_cooldown_bars=0,
        reentry_rank_gate_enabled=True,
        reentry_rank_gate_buffer=2,
        reentry_replace_policy="REQUIRE_FREE_SLOT_OR_REPLACE_WORST",
        reentry_trend_filter="NONE",
        charges_model="BPS",
        charges_bps=0.0,
        include_dp_charges=False,
    )

    with SessionLocal() as db:
        res = ps.run_portfolio_strategy_backtest(
            db,
            get_settings(),
            symbols=[
                UniverseSymbolRef(exchange="NSE", symbol="AAA"),
                UniverseSymbolRef(exchange="NSE", symbol="BBB"),
            ],
            config=cfg,
            allow_fetch=False,
        )

    bbb_trades = [t for t in res["trades"] if t["symbol"] == "NSE:BBB"]
    assert any(t["reason"] == "PORTFOLIO_ROTATE_OUT" for t in bbb_trades)

    aaa_trades = [t for t in res["trades"] if t["symbol"] == "NSE:AAA"]
    assert any(t.get("entry_reason") == "REENTRY_TREND" for t in aaa_trades)


def test_portfolio_strategy_reentry_cooldown_and_max_cap(monkeypatch) -> None:
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    get_settings.cache_clear()

    d = date(2025, 1, 2)
    aaa_closes = (
        [100.0] * 10
        + [103.0, 105.0, 104.0, 101.8, 101.8]
        + [100.0] * 4
        + [120.0, 110.0, 120.0]  # early trigger then later trigger
        + [130.0, 126.0, 126.0]  # ensure trailing stop exits the re-entry trade
        + [110.0, 130.0, 130.0]  # trigger again (should be blocked by max)
    )
    bbb_closes = [100.0] * len(aaa_closes)
    bars_by_symbol = {
        "AAA": _bars_5m_closes(d, aaa_closes),
        "BBB": _bars_5m_closes(d, bbb_closes),
    }

    def _stub_load_series(*_args, symbol: str, exchange: str, **_kwargs) -> list[dict]:
        assert exchange == "NSE"
        return bars_by_symbol[symbol]

    monkeypatch.setattr(ps, "load_series", _stub_load_series)

    cfg = PortfolioStrategyBacktestConfigIn(
        timeframe="5m",
        start_date=d,
        end_date=d,
        entry_dsl="PRICE() > 0",
        exit_dsl="PRICE() < 0",
        product="MIS",
        direction="LONG",
        initial_cash=100000.0,
        max_open_positions=2,
        allocation_mode="RANKING",
        ranking_metric="PERF_PCT",
        ranking_window=1,
        sizing_mode="PCT_EQUITY",
        position_size_pct=50.0,
        trailing_stop_pct=3.0,
        cooldown_bars=999,
        allow_reentry_after_trailing_stop=True,
        reentry_cooldown_bars=3,
        reentry_max_per_symbol_per_trend=1,
        reentry_rank_gate_enabled=True,
        reentry_rank_gate_buffer=2,
        reentry_replace_policy="REQUIRE_FREE_SLOT",
        reentry_trend_filter="NONE",
        charges_model="BPS",
        charges_bps=0.0,
        include_dp_charges=False,
    )

    with SessionLocal() as db:
        res = ps.run_portfolio_strategy_backtest(
            db,
            get_settings(),
            symbols=[
                UniverseSymbolRef(exchange="NSE", symbol="AAA"),
                UniverseSymbolRef(exchange="NSE", symbol="BBB"),
            ],
            config=cfg,
            allow_fetch=False,
        )

    aaa_trades = [t for t in res["trades"] if t["symbol"] == "NSE:AAA"]
    assert sum(1 for t in aaa_trades if t.get("entry_reason") == "REENTRY_TREND") == 1
