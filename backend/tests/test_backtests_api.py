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


def test_backtests_strategy_backtest_entry_exit_single_symbol() -> None:
    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    start = (now - timedelta(days=2)).date().isoformat()
    end = now.date().isoformat()

    res = client.post(
        "/api/backtests/runs",
        json={
            "kind": "STRATEGY",
            "title": "strategy",
            "universe": {
                "mode": "GROUP",
                "group_id": 123,
                "symbols": [{"symbol": "AAA", "exchange": "NSE"}],
            },
            "config": {
                "timeframe": "1d",
                "start_date": start,
                "end_date": end,
                "entry_dsl": "PRICE() > 0",
                "exit_dsl": "PRICE() > 1000000",
                "product": "CNC",
                "direction": "LONG",
                "initial_cash": 1000.0,
                "position_size_pct": 100.0,
                "stop_loss_pct": 0.0,
                "take_profit_pct": 0.0,
                "trailing_stop_pct": 0.0,
                "slippage_bps": 0.0,
                "charges_model": "BPS",
                "charges_bps": 0.0,
                "charges_broker": "zerodha",
                "include_dp_charges": False,
            },
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kind"] == "STRATEGY"
    assert body["status"] == "COMPLETED", body
    result = body["result"]
    assert "series" in result
    assert len(result["series"]["ts"]) == 3
    assert len(result["series"]["equity"]) == 3
    assert "metrics" in result
    assert "baselines" in result
    assert "start_to_end" in result["baselines"]


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


def test_backtests_portfolio_gate_symbol_blocks_rebalances() -> None:
    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    start = (now - timedelta(days=2)).date().isoformat()
    end = now.date().isoformat()

    with SessionLocal() as session:
        g = Group(name="PF_GATE_SYMBOL", kind="PORTFOLIO", description="test")
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
            "title": "pf_gate_symbol",
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
                "gate_source": "SYMBOL",
                "gate_symbol_exchange": "NSE",
                "gate_symbol": "AAA",
                "gate_dsl": "PRICE() > 1000000",
                "gate_min_coverage_pct": 90.0,
            },
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "COMPLETED", body
    assert body["result"]["meta"]["gate"]["source"] == "SYMBOL"
    series = body["result"]["series"]
    assert series["equity"][0] == 1000.0
    assert series["equity"][-1] == 1000.0
    actions = body["result"]["actions"]
    assert actions and actions[0].get("skipped") is True
    assert body["result"]["metrics"]["rebalance_skipped_count"] >= 1


def test_backtests_portfolio_gate_group_index_blocks_on_low_coverage() -> None:
    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    # Insert partial history for one member to force low coverage early.
    with SessionLocal() as session:
        for i, close in enumerate([10.0, 10.0]):
            ts = now - timedelta(days=1 - i)
            session.add(
                Candle(
                    symbol="DDD",
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

        g = Group(name="PF_GATE_GROUP", kind="PORTFOLIO", description="test")
        session.add(g)
        session.commit()
        session.refresh(g)
        session.add_all(
            [
                GroupMember(
                    group_id=g.id,
                    symbol="AAA",
                    exchange="NSE",
                    target_weight=1 / 3,
                ),
                GroupMember(
                    group_id=g.id,
                    symbol="BBB",
                    exchange="NSE",
                    target_weight=1 / 3,
                ),
                GroupMember(
                    group_id=g.id,
                    symbol="DDD",
                    exchange="NSE",
                    target_weight=1 / 3,
                ),
            ]
        )
        session.commit()
        group_id = g.id

    start = (now - timedelta(days=2)).date().isoformat()
    end = now.date().isoformat()

    res = client.post(
        "/api/backtests/runs",
        json={
            "kind": "PORTFOLIO",
            "title": "pf_gate_group",
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
                "gate_source": "GROUP_INDEX",
                "gate_dsl": "PRICE() > 0",
                "gate_min_coverage_pct": 90.0,
            },
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "COMPLETED", body
    gate = body["result"]["meta"]["gate"]
    assert gate["source"] == "GROUP_INDEX"
    assert gate["members_total"] == 3
    actions = body["result"]["actions"]
    assert len(actions) >= 1
    assert actions[0].get("skipped") is True
    assert actions[0].get("gate", {}).get("coverage", 0.0) < 0.9


def test_backtests_execution_backtest_costs_reduce_equity() -> None:
    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    start = (now - timedelta(days=2)).date().isoformat()
    end = now.date().isoformat()

    with SessionLocal() as session:
        g = Group(name="PF_EXEC", kind="PORTFOLIO", description="test")
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

    base_res = client.post(
        "/api/backtests/runs",
        json={
            "kind": "PORTFOLIO",
            "title": "pf_base",
            "universe": {"mode": "GROUP", "group_id": group_id, "symbols": []},
            "config": {
                "timeframe": "1d",
                "start_date": start,
                "end_date": end,
                "method": "TARGET_WEIGHTS",
                "cadence": "MONTHLY",
                "fill_timing": "CLOSE",
                "initial_cash": 1000.0,
                "budget_pct": 100.0,
                "max_trades": 10,
                "min_trade_value": 0.0,
                "slippage_bps": 0.0,
                "charges_bps": 0.0,
            },
        },
    )
    assert base_res.status_code == 200
    base_body = base_res.json()
    assert base_body["status"] == "COMPLETED", base_body

    exec_res = client.post(
        "/api/backtests/runs",
        json={
            "kind": "EXECUTION",
            "title": "exec",
            "universe": {"mode": "GROUP", "group_id": group_id, "symbols": []},
            "config": {
                "base_run_id": base_body["id"],
                "fill_timing": "CLOSE",
                "slippage_bps": 25.0,
                "charges_bps": 10.0,
            },
        },
    )
    assert exec_res.status_code == 200
    body = exec_res.json()
    assert body["status"] == "COMPLETED", body
    ideal_end = body["result"]["ideal"]["series"]["equity"][-1]
    real_end = body["result"]["realistic"]["series"]["equity"][-1]
    assert real_end <= ideal_end
    assert body["result"]["delta"]["end_equity_delta"] <= 0


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


def test_backtests_portfolio_risk_parity_weights_sane() -> None:
    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    symbols = ["RR1", "RR2", "RR3"]
    base = {"RR1": 100.0, "RR2": 200.0, "RR3": 300.0}
    daily_rets = {
        "RR1": [
            0.01,
            -0.01,
            0.012,
            -0.012,
            0.008,
            -0.008,
            0.01,
            -0.01,
            0.012,
            -0.012,
            0.008,
            -0.008,
        ],
        "RR2": [0.002] * 12,
        "RR3": [
            0.005,
            -0.004,
            0.006,
            -0.005,
            0.004,
            -0.003,
            0.005,
            -0.004,
            0.006,
            -0.005,
            0.004,
            -0.003,
        ],
    }

    with SessionLocal() as session:
        for sym in symbols:
            price = base[sym]
            for i, r in enumerate(daily_rets[sym]):
                price *= 1.0 + r
                ts = now - timedelta(days=11 - i)
                session.add(
                    Candle(
                        symbol=sym,
                        exchange="NSE",
                        timeframe="1d",
                        ts=ts,
                        open=price,
                        high=price,
                        low=price,
                        close=price,
                        volume=1000.0,
                    )
                )

        g = Group(name="PF_RP", kind="PORTFOLIO", description="test")
        session.add(g)
        session.commit()
        session.refresh(g)
        for sym in symbols:
            session.add(
                GroupMember(
                    group_id=g.id, symbol=sym, exchange="NSE", target_weight=None
                )
            )
        session.commit()
        group_id = g.id

    start = (now - timedelta(days=4)).date().isoformat()
    end = now.date().isoformat()

    res = client.post(
        "/api/backtests/runs",
        json={
            "kind": "PORTFOLIO",
            "title": "rp",
            "universe": {"mode": "GROUP", "group_id": group_id, "symbols": []},
            "config": {
                "timeframe": "1d",
                "start_date": start,
                "end_date": end,
                "method": "RISK_PARITY",
                "cadence": "MONTHLY",
                "initial_cash": 100000.0,
                "budget_pct": 100.0,
                "max_trades": 50,
                "min_trade_value": 0.0,
                "slippage_bps": 0.0,
                "charges_bps": 0.0,
                "risk_window": 5,
                "min_observations": 5,
                "min_weight": 0.0,
                "max_weight": 0.7,
            },
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "COMPLETED", body
    actions = body["result"]["actions"]
    assert actions
    first_targets = actions[0]["targets"]
    assert first_targets
    w_sum = sum(float(w) for _k, w in first_targets)
    assert abs(w_sum - 1.0) < 1e-6
    assert all(0.0 <= float(w) <= 0.7 + 1e-6 for _k, w in first_targets)


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


def test_backtests_delete_runs_requires_auth_and_deletes_owned() -> None:
    client.cookies.clear()
    resp_register = client.post(
        "/api/auth/register",
        json={"username": "bt_del", "password": "pw123456", "display_name": "BT Del"},
    )
    assert resp_register.status_code == 201
    resp_login = client.post(
        "/api/auth/login",
        json={"username": "bt_del", "password": "pw123456"},
    )
    assert resp_login.status_code == 200
    client.cookies.clear()
    client.cookies.update(resp_login.cookies)

    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    start = (now - timedelta(days=2)).date().isoformat()
    end = now.date().isoformat()

    res = client.post(
        "/api/backtests/runs",
        json={
            "kind": "SIGNAL",
            "title": "to_delete",
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
    run_id = int(res.json()["id"])

    del_res = client.request(
        "DELETE",
        "/api/backtests/runs",
        json={"ids": [run_id]},
    )
    assert del_res.status_code == 200
    body = del_res.json()
    assert body["deleted_ids"] == [run_id]

    get_res = client.get(f"/api/backtests/runs/{run_id}")
    assert get_res.status_code == 404
