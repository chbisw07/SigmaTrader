from __future__ import annotations

from app.services.ai_toolcalling.mcp_tools import mcp_tools_to_openai_tools


def test_get_positions_and_holdings_have_hints() -> None:
    tools = mcp_tools_to_openai_tools(
        [
            {"name": "get_positions", "description": "Return positions", "inputSchema": {"type": "object"}},
            {"name": "get_holdings", "description": "Return holdings", "inputSchema": {"type": "object"}},
        ]
    )
    by_name = {t["function"]["name"]: t["function"]["description"] for t in tools}
    assert "delivery" in by_name["get_holdings"].lower()
    assert "holdings" in by_name["get_positions"].lower()

