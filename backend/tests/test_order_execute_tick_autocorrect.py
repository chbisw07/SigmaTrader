from __future__ import annotations

import os
from typing import Any, Dict, List
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.auth import hash_password
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import Order, User

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_TRADINGVIEW_WEBHOOK_SECRET"] = "tick-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        user = User(
            username="tick-user",
            password_hash=hash_password("tick-password"),
            role="TRADER",
            display_name="Tick User",
        )
        session.add(user)
        session.commit()


def _create_waiting_order(*, side: str, price: float) -> int:
    payload: Dict[str, Any] = {
        "secret": "tick-secret",
        "platform": "TRADINGVIEW",
        "st_user_id": "tick-user",
        "strategy_name": f"tick-test-strategy-{uuid4().hex}",
        "symbol": "NSE:INFY",
        "exchange": "NSE",
        "interval": "5",
        "trade_details": {"order_action": side, "quantity": 1, "price": price},
    }
    response = client.post("/webhook/tradingview", json=payload)
    assert response.status_code == 201
    data = response.json()
    return int(data["order_id"])


class _DummyResult:
    def __init__(self, order_id: str) -> None:
        self.order_id = order_id


class _TickFailOnceThenSuccessClient:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []
        self._first = True

    def place_order(self, **params: Any) -> _DummyResult:
        self.calls.append(params)
        if self._first:
            self._first = False
            raise Exception(
                "Tick size for this script is 0.10. Kindly enter price in the multiple "
                "of tick size for this script"
            )
        return _DummyResult(order_id="TICK123")


def test_execute_order_autocorrects_buy_limit_price_to_tick(monkeypatch: Any) -> None:
    order_id = _create_waiting_order(side="BUY", price=3691.55)

    from app.api import orders as orders_api

    client_fake = _TickFailOnceThenSuccessClient()

    def _fake_get_client(db: Any, settings: Any) -> _TickFailOnceThenSuccessClient:
        return client_fake

    monkeypatch.setattr(orders_api, "_get_zerodha_client", _fake_get_client)

    response = client.post(f"/api/orders/{order_id}/execute")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SENT"
    assert data["zerodha_order_id"] == "TICK123"

    assert len(client_fake.calls) == 2
    assert client_fake.calls[0]["variety"] == "regular"
    assert client_fake.calls[1]["variety"] == "regular"
    assert client_fake.calls[1]["price"] == 3691.6  # BUY: ceil to 0.10

    with SessionLocal() as session:
        order = session.get(Order, order_id)
        assert order is not None
        assert order.status == "SENT"
        assert order.zerodha_order_id == "TICK123"
        assert order.price == 3691.6
        assert order.error_message is None


def test_execute_order_autocorrects_sell_limit_price_to_tick(monkeypatch: Any) -> None:
    order_id = _create_waiting_order(side="SELL", price=3691.55)

    from app.api import orders as orders_api

    client_fake = _TickFailOnceThenSuccessClient()

    def _fake_get_client(db: Any, settings: Any) -> _TickFailOnceThenSuccessClient:
        return client_fake

    monkeypatch.setattr(orders_api, "_get_zerodha_client", _fake_get_client)

    response = client.post(f"/api/orders/{order_id}/execute")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SENT"
    assert data["zerodha_order_id"] == "TICK123"

    assert len(client_fake.calls) == 2
    assert client_fake.calls[1]["price"] == 3691.5  # SELL: floor to 0.10

    with SessionLocal() as session:
        order = session.get(Order, order_id)
        assert order is not None
        assert order.status == "SENT"
        assert order.price == 3691.5
        assert order.error_message is None

