from __future__ import annotations

import asyncio

from app.clients.mcp_sse import McpSseClient


class ExternalMcpSessionManager:
    """Best-effort in-process cache of MCP clients for non-Kite servers."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._clients: dict[str, McpSseClient] = {}

    async def get_client(self, *, server_url: str) -> McpSseClient:
        key = (server_url or "").strip()
        if not key:
            raise ValueError("server_url is required.")
        async with self._lock:
            c = self._clients.get(key)
            if c is None:
                c = McpSseClient(server_url=key, timeout_seconds=30, endpoint_required=False)
                self._clients[key] = c
            return c

    async def reset(self) -> None:
        async with self._lock:
            items = list(self._clients.items())
            self._clients = {}
        for _k, c in items:
            try:
                await c.close()
            except Exception:
                pass


external_mcp_sessions = ExternalMcpSessionManager()

__all__ = ["ExternalMcpSessionManager", "external_mcp_sessions"]

