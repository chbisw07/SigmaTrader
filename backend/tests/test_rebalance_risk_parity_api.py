from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import Candle
from app.schemas.positions import HoldingRead

UTC = timezone.utc

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    os.environ["ST_CRYPTO_KEY"] = "test-rebalance-risk-parity-secret"
    get_settings.cache_clear()

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Avoid hitting external market data during tests.
    from app.services import market_data as md

    def _noop_fetch(*_args, **_kwargs) -> None:  # pragma: no cover
        return

    md._fetch_and_store_history = _noop_fetch  # type: ignore[attr-defined]

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

    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    with SessionLocal() as session:
        # Seed aligned daily candles for two symbols with different volatility.
        # AAA: +/-10% swings, BBB: +/-1% swings.
        aaa = 100.0
        bbb = 100.0
        for i in range(100):
            ts = now - timedelta(days=99 - i)
            aaa = aaa * (1.10 if i % 2 == 0 else 0.90)
            bbb = bbb * (1.01 if (i % 4) < 2 else 0.99)
            session.add(
                Candle(
                    symbol="AAA",
                    exchange="NSE",
                    timeframe="1d",
                    ts=ts,
                    open=aaa,
                    high=aaa,
                    low=aaa,
                    close=aaa,
                    volume=1000.0,
                )
            )
            session.add(
                Candle(
                    symbol="BBB",
                    exchange="NSE",
                    timeframe="1d",
                    ts=ts,
                    open=bbb,
                    high=bbb,
                    low=bbb,
                    close=bbb,
                    volume=1000.0,
                )
            )
        session.commit()


def _seed_portfolio_group() -> int:
    suffix = os.urandom(3).hex()
    res = client.post(
        "/api/groups/",
        json={"name": f"pf-risk-{suffix}", "kind": "PORTFOLIO", "description": "test"},
    )
    assert res.status_code == 200, res.text
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


def test_risk_parity_preview_derives_weights_and_uses_cache(monkeypatch) -> None:
    group_id = _seed_portfolio_group()

    def fake_list_holdings(*_args, **_kwargs):
        return [
            HoldingRead(
                symbol="AAA",
                exchange="NSE",
                quantity=10,
                average_price=90,
                last_price=100,
            ),
            HoldingRead(
                symbol="BBB",
                exchange="NSE",
                quantity=10,
                average_price=95,
                last_price=100,
            ),
        ]

    import app.services.rebalance as rebalance_service

    monkeypatch.setattr(rebalance_service, "list_holdings", fake_list_holdings)

    payload = {
        "target_kind": "GROUP",
        "group_id": group_id,
        "broker_name": "zerodha",
        "rebalance_method": "RISK_PARITY",
        "risk": {
            "window": "6M",
            "timeframe": "1d",
            "min_observations": 60,
            "min_weight": 0.0,
            "max_weight": 1.0,
            "max_iter": 2000,
            "tol": 1e-8,
        },
        "budget_pct": 1.0,
        "drift_band_abs_pct": 0.0,
        "drift_band_rel_pct": 0.0,
        "max_trades": 50,
        "min_trade_value": 0,
    }

    res1 = client.post("/api/rebalance/preview", json=payload)
    assert res1.status_code == 200, res1.text
    result1 = res1.json()["results"][0]
    derived1 = result1.get("derived_targets") or []
    assert len(derived1) == 2

    w_by_sym = {d["symbol"]: float(d["target_weight"]) for d in derived1}
    assert w_by_sym["BBB"] > w_by_sym["AAA"]

    rc_by_sym = {d["symbol"]: float(d["risk_contribution_share"]) for d in derived1}
    assert 0.40 <= rc_by_sym["AAA"] <= 0.60
    assert 0.40 <= rc_by_sym["BBB"] <= 0.60

    # Second run should hit cache (same as_of/alignment).
    res2 = client.post("/api/rebalance/preview", json=payload)
    assert res2.status_code == 200, res2.text
    derived2 = res2.json()["results"][0].get("derived_targets") or []
    assert any(bool(d.get("cache_hit")) for d in derived2)
