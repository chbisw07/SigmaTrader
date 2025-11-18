from __future__ import annotations

from typing import Any, Dict, List

from app.clients import ZerodhaClient


class FakeKite:
    def __init__(self) -> None:
        self.access_token: str | None = None
        self.placed_orders: List[Dict[str, Any]] = []
        self.placed_gtts: List[Dict[str, Any]] = []

    def set_access_token(self, access_token: str) -> None:
        self.access_token = access_token

    def place_order(self, **params: Any) -> Dict[str, Any]:
        self.placed_orders.append(params)
        return {"order_id": "12345", "status": "success"}

    def orders(self) -> List[Dict[str, Any]]:
        return [{"order_id": "12345", "status": "OPEN"}]

    def order_history(self, order_id: str) -> List[Dict[str, Any]]:
        return [{"order_id": order_id, "status": "COMPLETE"}]

    def positions(self) -> Dict[str, Any]:
        return {
            "net": [
                {
                    "tradingsymbol": "INFY",
                    "product": "CNC",
                    "quantity": 10,
                    "average_price": 1500.0,
                    "pnl": 100.0,
                }
            ]
        }

    def holdings(self) -> List[Dict[str, Any]]:
        return [
            {
                "tradingsymbol": "INFY",
                "quantity": 10,
                "average_price": 1500.0,
                "last_price": 1600.0,
            }
        ]

    def ltp(self, instruments: list[str]) -> Dict[str, Any]:
        # Minimal implementation for ZerodhaClient.get_ltp; return a
        # fixed last_price so tests that exercise guardrails can use it.
        return {instruments[0]: {"last_price": 100.0}}

    def margins(self, segment: str | None = None) -> Dict[str, Any]:
        return {
            "equity": {
                "available": {"cash": 100000.0},
                "utilised": {"debits": 0.0},
            }
        }

    def order_margins(self, params: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "total": 1234.5,
                "charges": {"brokerage": 10.0},
                "currency": "INR",
            }
        ]

    def place_gtt(
        self,
        trigger_type: str,
        tradingsymbol: str,
        exchange: str,
        trigger_values: List[float],
        last_price: float,
        orders: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        payload = {
            "trigger_type": trigger_type,
            "tradingsymbol": tradingsymbol,
            "exchange": exchange,
            "trigger_values": trigger_values,
            "last_price": last_price,
            "orders": orders,
        }
        self.placed_gtts.append(payload)
        return {"trigger_id": 9876, "status": "active"}

    def get_gtts(self) -> List[Dict[str, Any]]:
        return self.placed_gtts

    def delete_gtt(self, trigger_id: int) -> Dict[str, Any]:
        return {"trigger_id": trigger_id, "status": "deleted"}


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

    positions = client.list_positions()
    assert positions["net"][0]["tradingsymbol"] == "INFY"

    holdings = client.list_holdings()
    assert holdings[0]["tradingsymbol"] == "INFY"


def test_place_gtt_single_uses_underlying_kite_client() -> None:
    kite = FakeKite()
    client = ZerodhaClient(kite)

    result = client.place_gtt_single(
        tradingsymbol="INFY",
        exchange="NSE",
        transaction_type="BUY",
        quantity=5,
        product="CNC",
        trigger_price=950.0,
        order_price=940.0,
        last_price=945.0,
    )

    assert kite.placed_gtts, "Expected a GTT to be placed"
    payload = kite.placed_gtts[0]
    assert payload["trigger_type"] == "single"
    assert payload["tradingsymbol"] == "INFY"
    assert payload["exchange"] == "NSE"
    assert payload["trigger_values"] == [950.0]
    assert payload["orders"][0]["transaction_type"] == "BUY"
    assert payload["orders"][0]["quantity"] == 5
    assert payload["orders"][0]["order_type"] == "LIMIT"
    assert payload["orders"][0]["product"] == "CNC"
    assert payload["orders"][0]["price"] == 940.0
    assert result["trigger_id"] == 9876
