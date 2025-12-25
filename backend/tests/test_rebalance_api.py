from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.main import app
from app.schemas.positions import HoldingRead

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_CRYPTO_KEY"] = "test-rebalance-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    resp_register = client.post(
        "/api/auth/register",
        json={"username": "trader", "password": "secret123", "display_name": "Trader"},
    )
    assert resp_register.status_code == 201

    resp_login = client.post(
        "/api/auth/login",
        json={"username": "trader", "password": "secret123"},
    )
    assert resp_login.status_code == 200
    client.cookies.clear()
    client.cookies.update(resp_login.cookies)


def _seed_portfolio_group() -> int:
    suffix = os.urandom(3).hex()
    res = client.post(
        "/api/groups/",
        json={"name": f"pf-{suffix}", "kind": "PORTFOLIO", "description": "test"},
    )
    assert res.status_code == 200
    gid = int(res.json()["id"])

    res = client.post(
        f"/api/groups/{gid}/members",
        json={"symbol": "AAA", "exchange": "NSE", "target_weight": 0.5},
    )
    assert res.status_code == 200
    res = client.post(
        f"/api/groups/{gid}/members",
        json={"symbol": "BBB", "exchange": "NSE", "target_weight": 0.5},
    )
    assert res.status_code == 200
    return gid


def test_rebalance_preview_generates_scaled_trades(monkeypatch) -> None:
    group_id = _seed_portfolio_group()

    def fake_list_holdings(*_args, **_kwargs):
        # AAA overweight (800), BBB underweight (200) at price 100.
        return [
            HoldingRead(
                symbol="AAA",
                exchange="NSE",
                quantity=8,
                average_price=90,
                last_price=100,
            ),
            HoldingRead(
                symbol="BBB",
                exchange="NSE",
                quantity=2,
                average_price=95,
                last_price=100,
            ),
        ]

    import app.services.rebalance as rebalance_service

    monkeypatch.setattr(rebalance_service, "list_holdings", fake_list_holdings)

    res = client.post(
        "/api/rebalance/preview",
        json={
            "target_kind": "GROUP",
            "group_id": group_id,
            "broker_name": "zerodha",
            "budget_pct": 0.10,
            "drift_band_abs_pct": 0.02,
            "drift_band_rel_pct": 0.15,
            "max_trades": 10,
            "min_trade_value": 0,
        },
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["results"][0]["broker_name"] == "zerodha"
    trades = payload["results"][0]["trades"]
    assert len(trades) == 2
    sides = {t["side"] for t in trades}
    assert sides == {"BUY", "SELL"}
    summary = payload["results"][0]["summary"]
    assert summary["portfolio_value"] == 1000.0
    assert summary["budget"] == 100.0
    assert 0.32 < summary["scale"] < 0.35


def test_rebalance_execute_creates_run_and_orders(monkeypatch) -> None:
    group_id = _seed_portfolio_group()

    def fake_list_holdings(*_args, **_kwargs):
        return [
            HoldingRead(
                symbol="AAA",
                exchange="NSE",
                quantity=8,
                average_price=90,
                last_price=100,
            ),
            HoldingRead(
                symbol="BBB",
                exchange="NSE",
                quantity=2,
                average_price=95,
                last_price=100,
            ),
        ]

    import app.services.rebalance as rebalance_service

    monkeypatch.setattr(rebalance_service, "list_holdings", fake_list_holdings)

    res = client.post(
        "/api/rebalance/execute",
        json={
            "target_kind": "GROUP",
            "group_id": group_id,
            "broker_name": "zerodha",
            "budget_pct": 0.10,
            "drift_band_abs_pct": 0.02,
            "drift_band_rel_pct": 0.15,
            "max_trades": 10,
            "min_trade_value": 0,
            "mode": "MANUAL",
            "execution_target": "LIVE",
            "order_type": "MARKET",
            "product": "CNC",
            "idempotency_key": "test-run-1",
        },
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["results"]
    result = payload["results"][0]
    assert result["created_order_ids"]
    run = result["run"]
    assert run is not None
    assert run["group_id"] == group_id
    assert run["broker_name"] == "zerodha"
    assert run["status"] == "EXECUTED"
    assert len(run["orders"]) == 2

    # Idempotency: repeat should return same run id.
    res2 = client.post(
        "/api/rebalance/execute",
        json={
            "target_kind": "GROUP",
            "group_id": group_id,
            "broker_name": "zerodha",
            "budget_pct": 0.10,
            "drift_band_abs_pct": 0.02,
            "drift_band_rel_pct": 0.15,
            "max_trades": 10,
            "min_trade_value": 0,
            "mode": "MANUAL",
            "execution_target": "LIVE",
            "order_type": "MARKET",
            "product": "CNC",
            "idempotency_key": "test-run-1",
        },
    )
    assert res2.status_code == 200, res2.text
    payload2 = res2.json()
    assert payload2["results"][0]["run"]["id"] == run["id"]


def test_rebalance_holdings_preview_uses_equal_weight(monkeypatch) -> None:
    def fake_list_holdings(*_args, **_kwargs):
        # 2 holdings, equal-weight targets. Total value = 1000.
        return [
            HoldingRead(
                symbol="AAA",
                exchange="NSE",
                quantity=8,
                average_price=90,
                last_price=100,
            ),
            HoldingRead(
                symbol="BBB",
                exchange="NSE",
                quantity=2,
                average_price=95,
                last_price=100,
            ),
        ]

    import app.services.rebalance as rebalance_service

    monkeypatch.setattr(rebalance_service, "list_holdings", fake_list_holdings)

    res = client.post(
        "/api/rebalance/preview",
        json={
            "target_kind": "HOLDINGS",
            "broker_name": "zerodha",
            "budget_pct": 0.10,
            "drift_band_abs_pct": 0.0,
            "drift_band_rel_pct": 0.0,
            "max_trades": 10,
            "min_trade_value": 0,
        },
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    results = payload["results"]
    assert results and results[0]["target_kind"] == "HOLDINGS"
    # Equal weight implies moving AAA down, BBB up.
    sides = {t["side"] for t in results[0]["trades"]}
    assert sides == {"BUY", "SELL"}
