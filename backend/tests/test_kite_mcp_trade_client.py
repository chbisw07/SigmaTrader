from __future__ import annotations

import asyncio
import json

import pytest

from app.services.ai_trading_manager.broker_adapter import OrderIntent
from app.services.kite_mcp.trade import KiteMcpTradeClient


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def tools_call(self, *, name: str, arguments: dict) -> dict:
        self.calls.append((name, dict(arguments)))
        if name == "place_order":
            return {"content": [{"type": "text", "text": json.dumps({"order_id": "order-1"})}]}
        if name == "get_orders":
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            [
                                {
                                    "order_id": "order-1",
                                    "tradingsymbol": "SBIN",
                                    "transaction_type": "BUY",
                                    "product": "MIS",
                                    "quantity": 1,
                                    "order_type": "MARKET",
                                    "status": "COMPLETE",
                                }
                            ]
                        ),
                    }
                ]
            }
        return {"content": [{"type": "text", "text": json.dumps({"ok": True})}]}


def test_kite_mcp_trade_client_place_order_parses_order_id() -> None:
    sess = FakeSession()
    client = KiteMcpTradeClient(session=sess)  # type: ignore[arg-type]
    ack = asyncio.run(
        client.place_order(
            account_id="default",
            intent=OrderIntent(
                symbol="SBIN",
                side="BUY",
                qty=1,
                product="MIS",
                order_type="MARKET",
                idempotency_key="k1",
            ),
        )
    )
    assert ack.broker_order_id == "order-1"
    assert sess.calls and sess.calls[0][0] == "place_order"
    assert sess.calls[0][1]["tradingsymbol"] == "SBIN"


def test_kite_mcp_trade_client_get_orders_normalizes_rows() -> None:
    sess = FakeSession()
    client = KiteMcpTradeClient(session=sess)  # type: ignore[arg-type]
    rows = asyncio.run(client.get_orders())
    assert len(rows) == 1
    assert rows[0].broker_order_id == "order-1"
    assert rows[0].symbol == "SBIN"
    assert rows[0].side == "BUY"


def test_kite_mcp_trade_client_place_order_rejects_bad_order_type() -> None:
    sess = FakeSession()
    client = KiteMcpTradeClient(session=sess)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        asyncio.run(
            client.place_order(
                account_id="default",
                intent=OrderIntent(symbol="SBIN", side="BUY", qty=1, product="MIS", order_type="HACK"),
            )
        )
