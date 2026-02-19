from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict

from app.schemas.ai_trading_manager import BrokerOrder
from app.services.ai_trading_manager.broker_adapter import BrokerOrderAck, OrderIntent

from .session_manager import KiteMcpSession


def _extract_tool_text(res: dict[str, Any]) -> str:
    content = res.get("content")
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict):
            return str(first.get("text") or "")
    return ""


def _extract_tool_json(res: dict[str, Any]) -> Any:
    text = _extract_tool_text(res)
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return text


def _tag_from_idempotency_key(key: str | None) -> str | None:
    if not key:
        return None
    h = hashlib.sha256(str(key).encode("utf-8")).hexdigest()
    # Kite tags have a small limit; keep deterministic and short.
    return f"stai-{h[:12]}"


@dataclass(frozen=True)
class KiteMcpPlaceOrderResult:
    broker_order_id: str
    raw: Dict[str, Any]


class KiteMcpTradeClient:
    """Kite MCP trade tool wrapper (MCP tools/call).

    Important: this is NOT a REST client; it uses the already-initialized MCP
    session and only calls allowlisted trade tools with a validated argument set.
    """

    def __init__(self, *, session: KiteMcpSession) -> None:
        self._session = session

    async def place_order(self, *, account_id: str, intent: OrderIntent) -> BrokerOrderAck:
        # Minimal arg mapping aligned to Kite Connect naming.
        order_type = str(intent.order_type or "MARKET").upper()
        if order_type not in {"MARKET", "LIMIT", "SL", "SL-M"}:
            raise ValueError("order_type not allowed")
        product = str(intent.product or "CNC").upper()
        if product not in {"CNC", "MIS"}:
            raise ValueError("product not allowed")
        qty_i = int(float(intent.qty))
        if qty_i <= 0:
            raise ValueError("quantity must be positive")
        args: dict[str, Any] = {
            "exchange": "NSE",
            "tradingsymbol": str(intent.symbol).upper(),
            "transaction_type": str(intent.side).upper(),
            "quantity": qty_i,
            "product": product,
            "order_type": order_type,
            "validity": "DAY",
            "variety": "regular",
        }
        if intent.limit_price is not None and order_type in {"LIMIT", "SL"}:
            args["price"] = float(intent.limit_price)
        if intent.trigger_price is not None and order_type in {"SL", "SL-M"}:
            args["trigger_price"] = float(intent.trigger_price)
        tag = _tag_from_idempotency_key(intent.idempotency_key)
        if tag:
            args["tag"] = tag

        res = await self._session.tools_call(name="place_order", arguments=args)
        if isinstance(res, dict) and res.get("isError") is True:
            raise RuntimeError(_extract_tool_text(res) or "place_order failed")

        payload = _extract_tool_json(res) if isinstance(res, dict) else None
        broker_order_id = None
        if isinstance(payload, dict):
            broker_order_id = payload.get("order_id") or payload.get("broker_order_id")
            if isinstance(payload.get("data"), dict) and not broker_order_id:
                broker_order_id = payload["data"].get("order_id")
        if not broker_order_id:
            # Fall back to raw text (some MCP servers return a plain order id).
            t = _extract_tool_text(res) if isinstance(res, dict) else ""
            broker_order_id = (t or "").strip() or None
        if not broker_order_id:
            raise RuntimeError("place_order did not return an order_id")

        return BrokerOrderAck(broker_order_id=str(broker_order_id), status="ACK")

    async def cancel_order(self, *, broker_order_id: str) -> dict[str, Any]:
        args = {"order_id": str(broker_order_id)}
        res = await self._session.tools_call(name="cancel_order", arguments=args)
        if isinstance(res, dict) and res.get("isError") is True:
            raise RuntimeError(_extract_tool_text(res) or "cancel_order failed")
        return dict(res or {}) if isinstance(res, dict) else {"result": res}

    async def modify_order(self, *, broker_order_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        args: dict[str, Any] = {"order_id": str(broker_order_id)}
        # Allow only a small safe surface here; expand later.
        for k in ("quantity", "price", "trigger_price", "order_type", "validity"):
            if k in patch and patch[k] is not None:
                args[k] = patch[k]
        res = await self._session.tools_call(name="modify_order", arguments=args)
        if isinstance(res, dict) and res.get("isError") is True:
            raise RuntimeError(_extract_tool_text(res) or "modify_order failed")
        return dict(res or {}) if isinstance(res, dict) else {"result": res}

    async def get_orders(self) -> list[BrokerOrder]:
        res = await self._session.tools_call(name="get_orders", arguments={})
        if isinstance(res, dict) and res.get("isError") is True:
            raise RuntimeError(_extract_tool_text(res) or "get_orders failed")
        payload = _extract_tool_json(res) if isinstance(res, dict) else None
        rows = payload if isinstance(payload, list) else []
        out: list[BrokerOrder] = []
        for o in rows:
            if not isinstance(o, dict):
                continue
            try:
                out.append(
                    BrokerOrder(
                        broker_order_id=str(o.get("order_id") or ""),
                        symbol=str(o.get("tradingsymbol") or "").strip().upper(),
                        side=str(o.get("transaction_type") or "").strip().upper(),  # BUY/SELL
                        product=str(o.get("product") or "CNC").strip().upper(),
                        qty=float(o.get("quantity") or 0.0),
                        order_type=str(o.get("order_type") or "MARKET").strip().upper(),
                        status=str(o.get("status") or "UNKNOWN").strip().upper(),
                    )
                )
            except Exception:
                continue
        return out


__all__ = ["KiteMcpTradeClient", "KiteMcpPlaceOrderResult"]
