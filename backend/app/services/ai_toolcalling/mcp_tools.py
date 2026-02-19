from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List


_TOOL_DESC_HINTS: dict[str, str] = {
    # Users often confuse "positions" vs "holdings" in Kite. Make the distinction explicit
    # so the tool-caller chooses correctly.
    "get_positions": (
        "Note: this returns trading positions (net). It may NOT include long-term delivery holdings. "
        "For delivery/CNC holdings use get_holdings."
    ),
    "get_holdings": "Note: this returns delivery holdings (CNC). For open/intraday positions use get_positions.",
    "get_orders": (
        "Note: use this to inspect recent orders/trade status; positions/holdings may not show closed trades."
    ),
    "get_order_history": "Note: use this for order timeline/history; helpful for 'what did I do today' questions.",
    "get_trades": "Note: use this for executed trades/fills; helpful for 'today I bought/sold' questions.",
}


def mcp_tools_to_openai_tools(mcp_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for t in mcp_tools:
        if not isinstance(t, dict):
            continue
        name = str(t.get("name") or "").strip()
        if not name:
            continue
        desc = str(t.get("description") or "").strip() or f"MCP tool: {name}"
        hint = _TOOL_DESC_HINTS.get(name)
        if hint and hint not in desc:
            desc = f"{desc}\n\n{hint}"
        schema = t.get("inputSchema")
        if not isinstance(schema, dict):
            schema = {"type": "object", "properties": {}, "additionalProperties": True}
        out.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": schema,
                },
            }
        )
    return out


def hash_tool_definitions(openai_tools: List[Dict[str, Any]]) -> str:
    payload = json.dumps(openai_tools, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def tool_result_preview(value: Any, *, max_chars: int = 1200) -> str:
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        raw = str(value)
    if len(raw) > max_chars:
        return raw[:max_chars] + "…"
    return raw


__all__ = ["hash_tool_definitions", "mcp_tools_to_openai_tools", "tool_result_preview"]
