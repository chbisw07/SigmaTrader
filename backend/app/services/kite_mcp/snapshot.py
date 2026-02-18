from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.schemas.ai_trading_manager import BrokerOrder, BrokerPosition, BrokerSnapshot
from app.services.ai_trading_manager.ai_settings_config import get_ai_settings_with_source
from app.services.kite_mcp.secrets import get_auth_session_id
from app.services.kite_mcp.session_manager import kite_mcp_sessions


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


def _normalize_positions(payload: Any) -> List[BrokerPosition]:
    if payload is None:
        return []
    rows = []
    if isinstance(payload, dict) and isinstance(payload.get("net"), list):
        rows = payload.get("net") or []
    elif isinstance(payload, list):
        rows = payload
    else:
        return []

    out: List[BrokerPosition] = []
    for p in rows:
        if not isinstance(p, dict):
            continue
        try:
            out.append(
                BrokerPosition(
                    symbol=str(p.get("tradingsymbol") or p.get("symbol") or "").strip().upper(),
                    product=str(p.get("product") or "CNC").strip().upper(),
                    qty=float(p.get("quantity") or p.get("qty") or 0.0),
                    avg_price=float(p.get("average_price") or p.get("avg_price") or 0.0)
                    if (p.get("average_price") is not None or p.get("avg_price") is not None)
                    else None,
                )
            )
        except Exception:
            continue
    return out


def _normalize_orders(payload: Any) -> List[BrokerOrder]:
    if payload is None:
        return []
    rows = payload if isinstance(payload, list) else []
    out: List[BrokerOrder] = []
    for o in rows:
        if not isinstance(o, dict):
            continue
        try:
            out.append(
                BrokerOrder(
                    broker_order_id=str(o.get("order_id") or o.get("broker_order_id") or ""),
                    symbol=str(o.get("tradingsymbol") or o.get("symbol") or "").strip().upper(),
                    side=str(o.get("transaction_type") or o.get("side") or "").strip().upper(),  # BUY/SELL
                    product=str(o.get("product") or "CNC").strip().upper(),
                    qty=float(o.get("quantity") or o.get("qty") or 0.0),
                    order_type=str(o.get("order_type") or "MARKET").strip().upper(),
                    status=str(o.get("status") or "UNKNOWN").strip().upper(),
                )
            )
        except Exception:
            continue
    return out


async def fetch_kite_mcp_snapshot(
    db: Session,
    settings: Settings,
    *,
    account_id: str = "default",
) -> BrokerSnapshot:
    cfg, _src = get_ai_settings_with_source(db, settings)
    if not cfg.feature_flags.kite_mcp_enabled or not cfg.kite_mcp.server_url:
        raise RuntimeError("Kite MCP is not enabled or configured.")

    auth_sid = get_auth_session_id(db, settings)
    session = await kite_mcp_sessions.get_session(server_url=cfg.kite_mcp.server_url, auth_session_id=auth_sid)
    await session.ensure_initialized()

    # Helper for calling tools and surfacing common error.
    async def _call(name: str) -> Tuple[dict[str, Any], Any]:
        res = await session.tools_call(name=name, arguments={})
        if isinstance(res, dict) and res.get("isError") is True:
            raise RuntimeError(_extract_tool_text(res) or f"{name} failed.")
        return res, _extract_tool_json(res) if isinstance(res, dict) else None

    now = datetime.now(UTC)
    holdings_res, holdings = await _call("get_holdings")
    positions_res, positions_payload = await _call("get_positions")
    orders_res, orders_payload = await _call("get_orders")
    margins_res, margins_payload = await _call("get_margins")

    holdings_list: List[Dict[str, Any]] = []
    if isinstance(holdings, list):
        holdings_list = [h for h in holdings if isinstance(h, dict)]
    elif isinstance(holdings, dict) and isinstance(holdings.get("holdings"), list):
        holdings_list = [h for h in holdings.get("holdings") if isinstance(h, dict)]

    margins_dict: Dict[str, Any] = dict(margins_payload or {}) if isinstance(margins_payload, dict) else {}

    return BrokerSnapshot(
        as_of_ts=now,
        account_id=account_id,
        source="kite_mcp",
        holdings=holdings_list,
        positions=_normalize_positions(positions_payload),
        orders=_normalize_orders(orders_payload),
        margins=margins_dict,
        quotes_cache=[],
    )


__all__ = ["fetch_kite_mcp_snapshot"]

