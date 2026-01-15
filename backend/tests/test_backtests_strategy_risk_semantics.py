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


def _sma_series(closes: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    if period <= 0:
        return out
    window_sum = 0.0
    for i, c in enumerate(closes):
        window_sum += float(c)
        if i >= period:
            window_sum -= float(closes[i - period])
        if i >= period - 1:
            out[i] = window_sum / period
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


def test_strategy_reentry_after_trailing_stop_without_ma_cross(monkeypatch) -> None:
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    get_settings.cache_clear()

    d = date(2025, 1, 2)
    closes = (
        [100.0] * 50
        + [90.0] * 5
        + [120.0] * 10
        + [140.0] * 5
        + [150.0, 145.0, 130.0, 150.0, 150.0, 150.0]
    )
    bars = _bars_5m(d, closes)

    def _stub_load_series(*_args, symbol: str, exchange: str, **_kwargs) -> list[dict]:
        assert exchange == "NSE"
        assert symbol == "AAA"
        return bars

    monkeypatch.setattr(bs, "load_series", _stub_load_series)

    cfg = {
        "timeframe": "5m",
        "start_date": d,
        "end_date": d,
        "entry_dsl": "MA(9) CROSSES_ABOVE MA(45)",
        "exit_dsl": "PRICE() < 0",
        "product": "CNC",
        "direction": "LONG",
        "initial_cash": 100000.0,
        "position_size_pct": 100.0,
        "stop_loss_pct": 0.0,
        "take_profit_pct": 0.0,
        "trailing_stop_pct": 3.0,
        "allow_reentry_after_trailing_stop": True,
        "reentry_cooldown_bars": 1,
        "max_reentries_per_trend": 999,
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
    assert len(trades) == 2
    assert trades[0]["reason"] == "TRAILING_STOP"
    assert trades[1]["entry_reason"] == "REENTRY_TREND"


def test_strategy_reentry_blocked_when_trend_filter_fails(monkeypatch) -> None:
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    get_settings.cache_clear()

    d = date(2025, 1, 2)
    closes = (
        [100.0] * 50
        + [90.0] * 5
        + [120.0] * 10
        + [140.0] * 5
        + [150.0, 145.0]
        + [60.0] * 9
        + [65.0, 60.0, 65.0, 65.0]
    )
    bars = _bars_5m(d, closes)

    def _stub_load_series(*_args, symbol: str, exchange: str, **_kwargs) -> list[dict]:
        assert exchange == "NSE"
        assert symbol == "AAA"
        return bars

    monkeypatch.setattr(bs, "load_series", _stub_load_series)

    ma9 = _sma_series(closes, 9)
    ma45 = _sma_series(closes, 45)

    # Sanity: after the trailing-stop exit, there exists a bar that crosses above
    # the fast MA, but the trend filter is false (close below slow MA).
    exit_idx = 72  # 9:15 -> 15:15 at 5m bars
    assert any(
        i > exit_idx
        and ma9[i] is not None
        and ma9[i - 1] is not None
        and ma45[i] is not None
        and float(closes[i - 1]) <= float(ma9[i - 1])
        and float(closes[i]) > float(ma9[i])
        and not (float(closes[i]) > float(ma45[i]) and float(ma9[i]) >= float(ma45[i]))
        for i in range(exit_idx + 1, len(closes))
    )

    cfg = {
        "timeframe": "5m",
        "start_date": d,
        "end_date": d,
        "entry_dsl": "MA(9) CROSSES_ABOVE MA(45)",
        "exit_dsl": "PRICE() < 0",
        "product": "CNC",
        "direction": "LONG",
        "initial_cash": 100000.0,
        "position_size_pct": 100.0,
        "stop_loss_pct": 0.0,
        "take_profit_pct": 0.0,
        "trailing_stop_pct": 3.0,
        "allow_reentry_after_trailing_stop": True,
        "reentry_cooldown_bars": 0,
        "max_reentries_per_trend": 999,
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


def test_strategy_reentry_cooldown_respected(monkeypatch) -> None:
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    get_settings.cache_clear()

    d = date(2025, 1, 2)
    closes = (
        [100.0] * 50
        + [90.0] * 5
        + [120.0] * 10
        + [140.0] * 5
        + [150.0, 145.0]
        + [130.0, 150.0, 130.0, 150.0, 150.0, 150.0, 150.0, 150.0]
    )
    bars = _bars_5m(d, closes)

    def _stub_load_series(*_args, symbol: str, exchange: str, **_kwargs) -> list[dict]:
        assert exchange == "NSE"
        assert symbol == "AAA"
        return bars

    monkeypatch.setattr(bs, "load_series", _stub_load_series)

    cfg = {
        "timeframe": "5m",
        "start_date": d,
        "end_date": d,
        "entry_dsl": "MA(9) CROSSES_ABOVE MA(45)",
        "exit_dsl": "PRICE() < 0",
        "product": "CNC",
        "direction": "LONG",
        "initial_cash": 100000.0,
        "position_size_pct": 100.0,
        "stop_loss_pct": 0.0,
        "take_profit_pct": 0.0,
        "trailing_stop_pct": 3.0,
        "allow_reentry_after_trailing_stop": True,
        "reentry_cooldown_bars": 3,
        "max_reentries_per_trend": 999,
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
    assert len(trades) == 2
    assert trades[1]["entry_reason"] == "REENTRY_TREND"

    exit_dt = datetime.fromisoformat(trades[0]["exit_ts"])
    reentry_dt = datetime.fromisoformat(trades[1]["entry_ts"])
    assert reentry_dt - exit_dt == timedelta(minutes=20)  # 4 × 5m bars


def test_strategy_max_reentries_per_trend(monkeypatch) -> None:
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    get_settings.cache_clear()

    d = date(2025, 1, 2)
    closes = (
        [100.0] * 50
        + [90.0] * 5
        + [120.0] * 10
        + [140.0] * 5
        + [150.0, 145.0]
        + [130.0, 150.0]
        + [160.0, 155.0]
        + [140.0, 160.0, 160.0, 160.0]
    )
    bars = _bars_5m(d, closes)

    def _stub_load_series(*_args, symbol: str, exchange: str, **_kwargs) -> list[dict]:
        assert exchange == "NSE"
        assert symbol == "AAA"
        return bars

    monkeypatch.setattr(bs, "load_series", _stub_load_series)

    ma9 = _sma_series(closes, 9)
    ma45 = _sma_series(closes, 45)

    cfg = {
        "timeframe": "5m",
        "start_date": d,
        "end_date": d,
        "entry_dsl": "MA(9) CROSSES_ABOVE MA(45)",
        "exit_dsl": "PRICE() < 0",
        "product": "CNC",
        "direction": "LONG",
        "initial_cash": 100000.0,
        "position_size_pct": 100.0,
        "stop_loss_pct": 0.0,
        "take_profit_pct": 0.0,
        "trailing_stop_pct": 3.0,
        "allow_reentry_after_trailing_stop": True,
        "reentry_cooldown_bars": 0,
        "max_reentries_per_trend": 1,
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
    assert len(trades) == 2
    assert trades[1]["entry_reason"] == "REENTRY_TREND"
    assert trades[1]["reason"] == "TRAILING_STOP"

    second_exit_dt = datetime.fromisoformat(trades[1]["exit_ts"])
    start_dt = datetime.combine(d, time(9, 15), tzinfo=second_exit_dt.tzinfo)
    second_exit_idx = int((second_exit_dt - start_dt).total_seconds() // (5 * 60))

    # Sanity: after the second trailing-stop exit, a valid re-entry trigger exists
    # in a continuing trend, but max-reentries prevents scheduling a new trade.
    assert any(
        i > second_exit_idx
        and ma9[i] is not None
        and ma9[i - 1] is not None
        and ma45[i] is not None
        and float(closes[i - 1]) <= float(ma9[i - 1])
        and float(closes[i]) > float(ma9[i])
        and (float(closes[i]) > float(ma45[i]) and float(ma9[i]) >= float(ma45[i]))
        for i in range(second_exit_idx + 1, len(closes))
    )
