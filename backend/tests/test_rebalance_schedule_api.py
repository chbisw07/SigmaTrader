from __future__ import annotations

import os
from datetime import datetime

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.main import app
from app.schemas.positions import HoldingRead

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_CRYPTO_KEY"] = "test-rebalance-schedule-secret"
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
        json={"name": f"pf-sched-{suffix}", "kind": "PORTFOLIO", "description": "test"},
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


def test_schedule_get_put_roundtrip() -> None:
    group_id = _seed_portfolio_group()

    res = client.get(f"/api/rebalance/schedule?group_id={group_id}")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["group_id"] == group_id
    assert data["enabled"] is True
    assert data["config"]["timezone"] == "Asia/Kolkata"
    assert data["next_run_at"] is not None

    res2 = client.put(
        f"/api/rebalance/schedule?group_id={group_id}",
        json={
            "enabled": True,
            "config": {
                "frequency": "WEEKLY",
                "time_local": "15:10",
                "timezone": "Asia/Kolkata",
                "weekday": 4,
                "roll_to_trading_day": "NEXT",
            },
        },
    )
    assert res2.status_code == 200, res2.text
    data2 = res2.json()
    assert data2["config"]["frequency"] == "WEEKLY"
    assert data2["config"]["weekday"] == 4


def test_execute_updates_last_and_next(monkeypatch) -> None:
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

    res0 = client.get(f"/api/rebalance/schedule?group_id={group_id}")
    assert res0.status_code == 200
    before = res0.json()
    assert before["last_run_at"] is None

    res = client.post(
        "/api/rebalance/execute",
        json={
            "target_kind": "GROUP",
            "group_id": group_id,
            "broker_name": "zerodha",
            "budget_pct": 0.10,
            "drift_band_abs_pct": 0.0,
            "drift_band_rel_pct": 0.0,
            "max_trades": 10,
            "min_trade_value": 0,
            "mode": "MANUAL",
            "execution_target": "LIVE",
            "order_type": "MARKET",
            "product": "CNC",
            "idempotency_key": f"sched-{os.urandom(2).hex()}",
        },
    )
    assert res.status_code == 200, res.text

    res1 = client.get(f"/api/rebalance/schedule?group_id={group_id}")
    assert res1.status_code == 200, res1.text
    after = res1.json()
    assert after["last_run_at"] is not None
    assert after["next_run_at"] is not None

    # Sanity: next should be >= last (timezones ignored in naive storage).
    last_dt = datetime.fromisoformat(after["last_run_at"])
    next_dt = datetime.fromisoformat(after["next_run_at"])
    assert next_dt >= last_dt
