from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services import backtests_strategy as bs
from app.services.backtests_data import UniverseSymbolRef


def _bars_5m(d: date, closes: list[float]) -> list[dict]:
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


def test_strategy_trailing_stop_never_triggers_before_activation(monkeypatch) -> None:
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    get_settings.cache_clear()

    d = date(2025, 1, 2)
    bars = _bars_5m(d, [100.0, 100.0, 99.0, 96.0, 95.0, 95.0])

    def _stub_load_series(*_args, symbol: str, exchange: str, **_kwargs) -> list[dict]:
        assert exchange == "NSE"
        assert symbol == "AAA"
        return bars

    monkeypatch.setattr(bs, "load_series", _stub_load_series)

    cfg = {
        "timeframe": "5m",
        "start_date": d,
        "end_date": d,
        "entry_dsl": "PRICE() > 0",
        "exit_dsl": "PRICE() < 0",
        "product": "CNC",
        "direction": "LONG",
        "initial_cash": 10000.0,
        "position_size_pct": 100.0,
        "stop_loss_pct": 5.0,
        "take_profit_pct": 10.0,
        "trailing_stop_pct": 3.0,
        "slippage_bps": 0.0,
        "charges_model": "BPS",
        "charges_bps": 0.0,
        "include_dp_charges": False,
    }

    with SessionLocal() as db:
        res = bs.run_strategy_backtest(
            db,
            get_settings(),
            symbol=UniverseSymbolRef(exchange="NSE", symbol="AAA"),
            config=cfg,
            allow_fetch=False,
        )

    trades = res["trades"]
    assert len(trades) == 1
    assert trades[0]["reason"] == "STOP_LOSS"
    assert trades[0]["pnl_pct"] < 0


def test_strategy_trailing_activation_allows_breakeven_exit(monkeypatch) -> None:
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    get_settings.cache_clear()

    d = date(2025, 1, 2)
    bars = _bars_5m(d, [100.0, 100.0, 103.0, 100.0, 100.0])

    def _stub_load_series(*_args, symbol: str, exchange: str, **_kwargs) -> list[dict]:
        assert exchange == "NSE"
        assert symbol == "AAA"
        return bars

    monkeypatch.setattr(bs, "load_series", _stub_load_series)

    cfg = {
        "timeframe": "5m",
        "start_date": d,
        "end_date": d,
        "entry_dsl": "PRICE() > 0",
        "exit_dsl": "PRICE() < 0",
        "product": "CNC",
        "direction": "LONG",
        "initial_cash": 10000.0,
        "position_size_pct": 100.0,
        "stop_loss_pct": 0.0,
        "take_profit_pct": 0.0,
        "trailing_stop_pct": 3.0,
        "slippage_bps": 0.0,
        "charges_model": "BPS",
        "charges_bps": 0.0,
        "include_dp_charges": False,
    }

    with SessionLocal() as db:
        res = bs.run_strategy_backtest(
            db,
            get_settings(),
            symbol=UniverseSymbolRef(exchange="NSE", symbol="AAA"),
            config=cfg,
            allow_fetch=False,
        )

    trades = res["trades"]
    assert len(trades) == 1
    assert trades[0]["reason"] == "TRAILING_STOP"
    assert abs(float(trades[0]["pnl_pct"])) < 1e-9


def test_strategy_trailing_ratchet_does_not_loosen(monkeypatch) -> None:
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    get_settings.cache_clear()

    d = date(2025, 1, 2)
    bars = _bars_5m(d, [100.0, 100.0, 103.0, 105.0, 104.0, 101.8, 101.8])

    def _stub_load_series(*_args, symbol: str, exchange: str, **_kwargs) -> list[dict]:
        assert exchange == "NSE"
        assert symbol == "AAA"
        return bars

    monkeypatch.setattr(bs, "load_series", _stub_load_series)

    cfg = {
        "timeframe": "5m",
        "start_date": d,
        "end_date": d,
        "entry_dsl": "PRICE() > 0",
        "exit_dsl": "PRICE() < 0",
        "product": "CNC",
        "direction": "LONG",
        "initial_cash": 10000.0,
        "position_size_pct": 100.0,
        "stop_loss_pct": 0.0,
        "take_profit_pct": 0.0,
        "trailing_stop_pct": 3.0,
        "slippage_bps": 0.0,
        "charges_model": "BPS",
        "charges_bps": 0.0,
        "include_dp_charges": False,
    }

    with SessionLocal() as db:
        res = bs.run_strategy_backtest(
            db,
            get_settings(),
            symbol=UniverseSymbolRef(exchange="NSE", symbol="AAA"),
            config=cfg,
            allow_fetch=False,
        )

    trades = res["trades"]
    assert len(trades) == 1
    assert trades[0]["reason"] == "TRAILING_STOP"
    assert float(trades[0]["exit_price"]) == 101.8
    assert trades[0]["pnl_pct"] > 0


def test_strategy_trailing_stop_short_symmetry(monkeypatch) -> None:
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    get_settings.cache_clear()

    d = date(2025, 1, 2)
    bars = _bars_5m(d, [100.0, 100.0, 97.0, 100.0, 100.0])

    def _stub_load_series(*_args, symbol: str, exchange: str, **_kwargs) -> list[dict]:
        assert exchange == "NSE"
        assert symbol == "AAA"
        return bars

    monkeypatch.setattr(bs, "load_series", _stub_load_series)

    cfg = {
        "timeframe": "5m",
        "start_date": d,
        "end_date": d,
        "entry_dsl": "PRICE() > 0",
        "exit_dsl": "PRICE() < 0",
        "product": "MIS",
        "direction": "SHORT",
        "initial_cash": 10000.0,
        "position_size_pct": 100.0,
        "stop_loss_pct": 0.0,
        "take_profit_pct": 0.0,
        "trailing_stop_pct": 3.0,
        "slippage_bps": 0.0,
        "charges_model": "BPS",
        "charges_bps": 0.0,
        "include_dp_charges": False,
    }

    with SessionLocal() as db:
        res = bs.run_strategy_backtest(
            db,
            get_settings(),
            symbol=UniverseSymbolRef(exchange="NSE", symbol="AAA"),
            config=cfg,
            allow_fetch=False,
        )

    trades = res["trades"]
    assert len(trades) == 1
    assert trades[0]["reason"] == "TRAILING_STOP"
    assert abs(float(trades[0]["pnl_pct"])) < 1e-9


def test_strategy_take_profit_precedence_over_exit_signal(monkeypatch) -> None:
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    get_settings.cache_clear()

    d = date(2025, 1, 2)
    bars = _bars_5m(d, [100.0, 100.0, 103.0, 103.0])

    def _stub_load_series(*_args, symbol: str, exchange: str, **_kwargs) -> list[dict]:
        assert exchange == "NSE"
        assert symbol == "AAA"
        return bars

    monkeypatch.setattr(bs, "load_series", _stub_load_series)

    cfg = {
        "timeframe": "5m",
        "start_date": d,
        "end_date": d,
        "entry_dsl": "PRICE() > 0",
        "exit_dsl": "PRICE() >= 103",
        "product": "CNC",
        "direction": "LONG",
        "initial_cash": 10000.0,
        "position_size_pct": 100.0,
        "stop_loss_pct": 0.0,
        "take_profit_pct": 3.0,
        "trailing_stop_pct": 0.0,
        "slippage_bps": 0.0,
        "charges_model": "BPS",
        "charges_bps": 0.0,
        "include_dp_charges": False,
    }

    with SessionLocal() as db:
        res = bs.run_strategy_backtest(
            db,
            get_settings(),
            symbol=UniverseSymbolRef(exchange="NSE", symbol="AAA"),
            config=cfg,
            allow_fetch=False,
        )

    trades = res["trades"]
    assert len(trades) == 1
    assert trades[0]["reason"] == "TAKE_PROFIT"
