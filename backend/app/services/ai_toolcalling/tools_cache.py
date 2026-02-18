from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, List

from .mcp_tools import hash_tool_definitions, mcp_tools_to_openai_tools


@dataclass(frozen=True)
class CachedTools:
    fetched_at_ts: float
    mcp_tools: List[Dict[str, Any]]
    openai_tools: List[Dict[str, Any]]
    tools_hash: str


_LOCK = asyncio.Lock()
_CACHE: dict[str, CachedTools] = {}


async def get_tools_cached(
    *,
    server_url: str,
    session,
    ttl_seconds: float = 300,
) -> tuple[CachedTools, bool]:
    now = time.time()
    key = (server_url or "").strip().lower()
    if not key:
        raise ValueError("server_url is required.")

    async with _LOCK:
        c = _CACHE.get(key)
        if c and (now - c.fetched_at_ts) < float(ttl_seconds):
            return c, False

        tools_resp = await session.tools_list()
        rows = tools_resp.get("tools") if isinstance(tools_resp, dict) else []
        mcp_tools = [t for t in rows if isinstance(t, dict)] if isinstance(rows, list) else []
        openai_tools = mcp_tools_to_openai_tools(mcp_tools)
        tools_hash = hash_tool_definitions(openai_tools)
        out = CachedTools(
            fetched_at_ts=now,
            mcp_tools=mcp_tools,
            openai_tools=openai_tools,
            tools_hash=tools_hash,
        )
        _CACHE[key] = out
        return out, True


__all__ = ["CachedTools", "get_tools_cached"]
