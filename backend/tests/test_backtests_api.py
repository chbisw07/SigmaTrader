from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app  # noqa: F401  # ensure routes are imported
from app.models import Candle, Group, GroupMember

UTC = timezone.utc

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Avoid hitting external market data during tests.
    from app.services import market_data as md

    def _noop_fetch(*_args, **_kwargs) -> None:  # pragma: no cover
        return

    md._fetch_and_store_history = _noop_fetch  # type: ignore[attr-defined]

    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    with SessionLocal() as session:
        for i, close in enumerate([100.0, 101.0, 99.5]):
            ts = now - timedelta(days=2 - i)
            session.add(
                Candle(
                    symbol="AAA",
                    exchange="NSE",
                    timeframe="1d",
                    ts=ts,
                    open=close,
                    high=close,
                    low=close,
                    close=close,
                    volume=1000.0,
                )
            )
        for i, close in enumerate([200.0, 202.0, 204.0]):
            ts = now - timedelta(days=2 - i)
            session.add(
                Candle(
                    symbol="BBB",
                    exchange="NSE",
                    timeframe="1d",
                    ts=ts,
                    open=close,
                    high=close,
                    low=close,
                    close=close,
                    volume=1000.0,
                )
            )
        session.commit()


def test_backtests_runs_roundtrip() -> None:
    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    start = (now - timedelta(days=2)).date().isoformat()
    end = now.date().isoformat()

    res = client.post(
        "/api/backtests/runs",
        json={
            "kind": "SIGNAL",
            "title": "test",
            "universe": {
                "mode": "GROUP",
                "group_id": 123,
                "symbols": [
                    {"symbol": "AAA", "exchange": "NSE"},
                    {"symbol": "BBB", "exchange": "NSE"},
                ],
            },
            "config": {
                "timeframe": "1d",
                "start_date": start,
                "end_date": end,
                "mode": "DSL",
                "dsl": "PRICE() > 0",
                "forward_windows": [1],
            },
        },
    )
    assert res.status_code == 200
    run = res.json()
    assert run["kind"] == "SIGNAL"
    assert run["status"] == "COMPLETED"
    assert run["title"] == "test"
    assert run["config"]["config"]["dsl"] == "PRICE() > 0"
    assert run["result"]["meta"]["symbols_requested"] == 2
    assert run["result"]["by_window"]["1"]["count"] == 4

    res2 = client.get("/api/backtests/runs?limit=10")
    assert res2.status_code == 200
    runs = res2.json()
    assert isinstance(runs, list)
    assert runs and runs[0]["id"] == run["id"]

    res3 = client.get(f"/api/backtests/runs/{run['id']}")
    assert res3.status_code == 200
    assert res3.json()["id"] == run["id"]


def test_backtests_signal_backtest_basic_metrics() -> None:
    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    start = (now - timedelta(days=2)).date().isoformat()
    end = now.date().isoformat()

    res = client.post(
        "/api/backtests/runs",
        json={
            "kind": "SIGNAL",
            "title": "perf_pct",
            "universe": {
                "mode": "GROUP",
                "group_id": 123,
                "symbols": [
                    {"symbol": "AAA", "exchange": "NSE"},
                    {"symbol": "BBB", "exchange": "NSE"},
                ],
            },
            "config": {
                "timeframe": "1d",
                "start_date": start,
                "end_date": end,
                "mode": "DSL",
                "dsl": "PERF_PCT(1) > 0",
                "forward_windows": [1],
            },
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "COMPLETED", body
    win = body["result"]["by_window"]["1"]
    assert win["count"] == 2
    assert win["win_rate_pct"] == 50.0


def test_backtests_portfolio_target_weights_basic_run() -> None:
    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    start = (now - timedelta(days=2)).date().isoformat()
    end = now.date().isoformat()

    with SessionLocal() as session:
        g = Group(name="PF_TEST", kind="PORTFOLIO", description="test")
        session.add(g)
        session.commit()
        session.refresh(g)
        session.add_all(
            [
                GroupMember(
                    group_id=g.id,
                    symbol="AAA",
                    exchange="NSE",
                    target_weight=0.5,
                ),
                GroupMember(
                    group_id=g.id,
                    symbol="BBB",
                    exchange="NSE",
                    target_weight=0.5,
                ),
            ]
        )
        session.commit()
        group_id = g.id

    res = client.post(
        "/api/backtests/runs",
        json={
            "kind": "PORTFOLIO",
            "title": "pf",
            "universe": {"mode": "GROUP", "group_id": group_id, "symbols": []},
            "config": {
                "timeframe": "1d",
                "start_date": start,
                "end_date": end,
                "method": "TARGET_WEIGHTS",
                "cadence": "MONTHLY",
                "initial_cash": 1000.0,
                "budget_pct": 100.0,
                "max_trades": 10,
                "min_trade_value": 0.0,
                "slippage_bps": 0.0,
                "charges_bps": 0.0,
            },
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "COMPLETED", body
    series = body["result"]["series"]
    assert len(series["dates"]) == 3
    assert len(series["equity"]) == 3
    assert series["equity"][0] == 1000.0
    assert series["equity"][-1] == 1005.5


def test_backtests_portfolio_rotation_top_n_momentum() -> None:
    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    with SessionLocal() as session:
        for i, close in enumerate([100.0, 120.0, 130.0]):
            ts = now - timedelta(days=2 - i)
            session.add(
                Candle(
                    symbol="CCC",
                    exchange="NSE",
                    timeframe="1d",
                    ts=ts,
                    open=close,
                    high=close,
                    low=close,
                    close=close,
                    volume=1000.0,
                )
            )
        g = Group(name="PF_ROT", kind="PORTFOLIO", description="test")
        session.add(g)
        session.commit()
        session.refresh(g)
        session.add_all(
            [
                GroupMember(
                    group_id=g.id,
                    symbol="AAA",
                    exchange="NSE",
                    target_weight=None,
                ),
                GroupMember(
                    group_id=g.id,
                    symbol="BBB",
                    exchange="NSE",
                    target_weight=None,
                ),
                GroupMember(
                    group_id=g.id,
                    symbol="CCC",
                    exchange="NSE",
                    target_weight=None,
                ),
            ]
        )
        session.commit()
        group_id = g.id

    start = (now - timedelta(days=1)).date().isoformat()
    end = now.date().isoformat()

    res = client.post(
        "/api/backtests/runs",
        json={
            "kind": "PORTFOLIO",
            "title": "rot",
            "universe": {"mode": "GROUP", "group_id": group_id, "symbols": []},
            "config": {
                "timeframe": "1d",
                "start_date": start,
                "end_date": end,
                "method": "ROTATION",
                "cadence": "MONTHLY",
                "initial_cash": 1000.0,
                "budget_pct": 100.0,
                "max_trades": 50,
                "min_trade_value": 0.0,
                "slippage_bps": 0.0,
                "charges_bps": 0.0,
                "top_n": 1,
                "ranking_window": 1,
            },
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "COMPLETED", body
    series = body["result"]["series"]
    assert len(series["dates"]) == 2
    assert series["equity"][-1] == 1080.0


def test_backtests_eod_candles_loader() -> None:
    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    start = (now - timedelta(days=10)).isoformat()
    end = (now + timedelta(days=1)).isoformat()
    res = client.post(
        "/api/backtests/candles/eod",
        json={
            "symbols": [
                {"symbol": "AAA", "exchange": "NSE"},
                {"symbol": "BBB", "exchange": "NSE"},
                {"symbol": "MISSING", "exchange": "NSE"},
            ],
            "start": start,
            "end": end,
            "allow_fetch": False,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["missing_symbols"] == ["NSE:MISSING"]
    assert "NSE:AAA" in body["prices"]
    assert "NSE:BBB" in body["prices"]
    assert len(body["dates"]) == 3
    assert body["prices"]["NSE:AAA"] == [100.0, 101.0, 99.5]
    assert body["prices"]["NSE:BBB"] == [200.0, 202.0, 204.0]
