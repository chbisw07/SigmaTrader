from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.main import app

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_CRYPTO_KEY"] = "test-buy-basket-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_buy_basket_creates_portfolio_and_orders(monkeypatch) -> None:
    # Login (buy requires an authenticated user).
    res = client.post(
        "/api/auth/register",
        json={"username": "buyer", "password": "pass1234", "display_name": "Buyer"},
    )
    assert res.status_code in (200, 201)
    res = client.post("/api/auth/login", json={"username": "buyer", "password": "pass1234"})
    assert res.status_code == 200
    client.cookies.clear()
    client.cookies.update(res.cookies)

    # Create basket group.
    res = client.post(
        "/api/groups/",
        json={"name": "b-buy", "kind": "MODEL_PORTFOLIO", "description": "t"},
    )
    assert res.status_code == 200
    basket_id = res.json()["id"]

    # Add members.
    res = client.post(
        f"/api/groups/{basket_id}/members",
        json={"symbol": "ABC", "exchange": "NSE", "target_weight": 0.6},
    )
    assert res.status_code == 200
    res = client.post(
        f"/api/groups/{basket_id}/members",
        json={"symbol": "XYZ", "exchange": "NSE", "target_weight": 0.4},
    )
    assert res.status_code == 200

    # Update basket config.
    res = client.patch(
        f"/api/groups/{basket_id}/basket/config",
        json={"funds": 100000, "allocation_mode": "WEIGHT"},
    )
    assert res.status_code == 200

    # Freeze prices.
    def fake_get_bulk_quotes(_db, _settings, keys):
        _ = keys
        return {
            ("NSE", "ABC"): {"last_price": 101.0, "prev_close": 100.0},
            ("NSE", "XYZ"): {"last_price": 201.0, "prev_close": 200.0},
        }

    monkeypatch.setattr(
        "app.services.baskets.get_bulk_quotes",
        fake_get_bulk_quotes,
        raising=True,
    )
    res = client.post(f"/api/groups/{basket_id}/basket/freeze")
    assert res.status_code == 200
    frozen = res.json()
    assert frozen["frozen_at"] is not None

    # Buy basket -> portfolio + orders.
    res = client.post(
        f"/api/groups/{basket_id}/buy",
        json={
            "broker_name": "zerodha",
            "product": "CNC",
            "order_type": "MARKET",
            "execution_target": "PAPER",
            "items": [
                {"symbol": "ABC", "exchange": "NSE", "qty": 5},
                {"symbol": "XYZ", "exchange": "NSE", "qty": 2},
            ],
        },
    )
    assert res.status_code == 200
    data = res.json()
    portfolio = data["portfolio_group"]
    orders = data["orders"]

    assert portfolio["kind"] == "PORTFOLIO"
    assert portfolio["origin_basket_id"] == basket_id
    assert portfolio["bought_at"] is not None
    assert portfolio["frozen_at"] == frozen["frozen_at"]
    assert portfolio["member_count"] == 2

    by_symbol = {m["symbol"]: m for m in portfolio["members"]}
    assert by_symbol["ABC"]["frozen_price"] == 101.0
    assert by_symbol["XYZ"]["frozen_price"] == 201.0

    assert len(orders) == 2
    for o in orders:
        assert o["portfolio_group_id"] == portfolio["id"]
        assert o["status"] == "WAITING"
        assert o["side"] == "BUY"
        assert o["order_type"] == "MARKET"
        assert o["product"] == "CNC"
        assert o["execution_target"] == "PAPER"
