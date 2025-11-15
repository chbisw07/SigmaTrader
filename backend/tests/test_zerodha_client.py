from __future__ import annotations

from typing import Any, Dict, List

from app.clients import ZerodhaClient


class FakeKite:
    def __init__(self) -> None:
        self.access_token: str | None = None
        self.placed_orders: List[Dict[str, Any]] = []

    def set_access_token(self, access_token: str) -> None:
        self.access_token = access_token

    def place_order(self, **params: Any) -> Dict[str, Any]:
        self.placed_orders.append(params)
        return {"order_id": "12345", "status": "success"}

    def orders(self) -> List[Dict[str, Any]]:
        return [{"order_id": "12345", "status": "OPEN"}]

    def order_history(self, order_id: str) -> List[Dict[str, Any]]:
        return [{"order_id": order_id, "status": "COMPLETE"}]


def test_place_order_uses_underlying_kite_client() -> None:
    kite = FakeKite()
    client = ZerodhaClient(kite)

    result = client.place_order(
        tradingsymbol="INFY",
        transaction_type="BUY",
        quantity=10,
        order_type="MARKET",
        product="MIS",
        exchange="NSE",
    )

    assert result.order_id == "12345"
    assert len(kite.placed_orders) == 1
    params = kite.placed_orders[0]
    assert params["tradingsymbol"] == "INFY"
    assert params["transaction_type"] == "BUY"
    assert params["quantity"] == 10
    assert params["order_type"] == "MARKET"
    assert params["product"] == "MIS"
    assert params["exchange"] == "NSE"


def test_list_orders_and_history_delegate_to_kite() -> None:
    kite = FakeKite()
    client = ZerodhaClient(kite)

    orders = client.list_orders()
    assert orders and orders[0]["order_id"] == "12345"

    history = client.get_order_history("12345")
    assert history and history[0]["status"] == "COMPLETE"
