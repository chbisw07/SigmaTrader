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
    os.environ["ST_CRYPTO_KEY"] = "test-rebalance-rotation-secret"
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
        # Seed daily candles so rotation scores and missing prices can resolve.
        closes = {"AAA": 100.0, "BBB": 50.0, "CCC": 200.0}
        for sym, close in closes.items():
            for i in range(5):
                ts = now - timedelta(days=4 - i)
                session.add(
                    Candle(
                        symbol=sym,
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


def _create_strategy_with_overlay() -> tuple[int, int]:
    res = client.post(
        "/api/signal-strategies/",
        json={
            "name": f"rot-{os.urandom(3).hex()}",
            "description": "rotation test",
            "tags": [],
            "regimes": [],
            "scope": "USER",
            "version": {
                "inputs": [{"name": "TF", "type": "timeframe", "default": "1d"}],
                "variables": [],
                "outputs": [
                    {
                        "name": "score",
                        "kind": "OVERLAY",
                        "dsl": "CLOSE(TF)",
                    }
                ],
                "enabled": True,
            },
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()
    strategy_id = int(data["id"])
    version_id = int(data["latest"]["id"])
    return strategy_id, version_id


def _seed_portfolio_group(symbols: list[str]) -> int:
    suffix = os.urandom(3).hex()
    res = client.post(
        "/api/groups/",
        json={"name": f"pf-rot-{suffix}", "kind": "PORTFOLIO", "description": "test"},
    )
    assert res.status_code == 200, res.text
    gid = int(res.json()["id"])

    # Seed equal target weights initially; rotation should override.
    per = 1.0 / len(symbols)
    for sym in symbols:
        res_m = client.post(
            f"/api/groups/{gid}/members",
            json={"symbol": sym, "exchange": "NSE", "target_weight": per},
        )
        assert res_m.status_code == 200, res_m.text
    return gid


def _seed_universe_group(symbols: list[str]) -> int:
    suffix = os.urandom(3).hex()
    res = client.post(
        "/api/groups/",
        json={"name": f"univ-{suffix}", "kind": "WATCHLIST", "description": "test"},
    )
    assert res.status_code == 200, res.text
    gid = int(res.json()["id"])
    for sym in symbols:
        res_m = client.post(
            f"/api/groups/{gid}/members",
            json={"symbol": sym, "exchange": "NSE"},
        )
        assert res_m.status_code == 200, res_m.text
    return gid


def test_signal_rotation_preview_derives_targets_and_trades(monkeypatch) -> None:
    _strategy_id, version_id = _create_strategy_with_overlay()
    group_id = _seed_portfolio_group(["AAA", "BBB"])
    universe_id = _seed_universe_group(["AAA", "BBB", "CCC"])

    def fake_list_holdings(*_args, **_kwargs):
        # Total value = 1500 (AAA 1000 + BBB 500).
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
                average_price=45,
                last_price=50,
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
            "rebalance_method": "SIGNAL_ROTATION",
            "rotation": {
                "signal_strategy_version_id": version_id,
                "signal_output": "score",
                "signal_params": {},
                "universe_group_id": universe_id,
                "top_n": 2,
                "weighting": "EQUAL",
                "sell_not_in_top_n": True,
                "require_positive_score": True,
            },
            "budget_pct": 1.0,
            "drift_band_abs_pct": 0.0,
            "drift_band_rel_pct": 0.0,
            "max_trades": 50,
            "min_trade_value": 0,
        },
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    result = payload["results"][0]
    derived = result.get("derived_targets") or []
    assert [d["symbol"] for d in derived] == ["CCC", "AAA"]
    assert derived[0]["rank"] == 1 and derived[0]["target_weight"] == 0.5
    assert derived[1]["rank"] == 2 and derived[1]["target_weight"] == 0.5

    trades = result["trades"]
    sides_by_symbol = {t["symbol"]: t["side"] for t in trades}
    assert sides_by_symbol["BBB"] == "SELL"
    assert sides_by_symbol["CCC"] == "BUY"

    # Audit: symbol outside top-N should carry rotation reason.
    bbb = next(t for t in trades if t["symbol"] == "BBB")
    assert bbb["reason"]["rotation"]["included"] is False
    assert bbb["reason"]["rotation"]["reason"] == "not_in_top_n"


def test_signal_rotation_blacklist_excludes_symbol(monkeypatch) -> None:
    _strategy_id, version_id = _create_strategy_with_overlay()
    group_id = _seed_portfolio_group(["AAA", "BBB"])
    universe_id = _seed_universe_group(["AAA", "BBB", "CCC"])

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
                average_price=45,
                last_price=50,
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
            "rebalance_method": "SIGNAL_ROTATION",
            "rotation": {
                "signal_strategy_version_id": version_id,
                "signal_output": "score",
                "signal_params": {},
                "universe_group_id": universe_id,
                "top_n": 1,
                "weighting": "EQUAL",
                "sell_not_in_top_n": True,
                "symbol_blacklist": ["CCC"],
                "require_positive_score": True,
            },
            "budget_pct": 1.0,
            "drift_band_abs_pct": 0.0,
            "drift_band_rel_pct": 0.0,
            "max_trades": 50,
            "min_trade_value": 0,
        },
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    derived = payload["results"][0].get("derived_targets") or []
    assert [d["symbol"] for d in derived] == ["AAA"]
    assert derived[0]["target_weight"] == 1.0
