from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from app.clients.mcp_sse import McpSseClient


def _set_query_param(url: str, *, key: str, value: str) -> str:
    p = urlparse(url)
    qs = parse_qs(p.query or "", keep_blank_values=True)
    qs[str(key)] = [str(value)]
    q2 = urlencode(qs, doseq=True)
    return urlunparse(p._replace(query=q2))


@dataclass
class KiteMcpSessionState:
    server_url: str
    auth_session_id: str | None = None
    server_info: Dict[str, Any] | None = None
    capabilities: Dict[str, Any] | None = None


class KiteMcpSession:
    def __init__(self, *, server_url: str, auth_session_id: str | None) -> None:
        self._base_server_url = (server_url or "").strip().rstrip("/")
        self.state = KiteMcpSessionState(server_url=self._base_server_url, auth_session_id=auth_session_id)
        self._client = McpSseClient(server_url=self._sse_url(), timeout_seconds=30, http2=True)
        self._initialized = False
        self._initialized_connect_seq: int | None = None
        self._lock = asyncio.Lock()

    def _sse_url(self) -> str:
        sse_url = self._base_server_url
        if self.state.auth_session_id:
            # Best-effort session reuse. The Kite MCP login flow embeds a
            # `session_id` token; the server appears to accept it as a query
            # parameter on /sse.
            sse_url = _set_query_param(sse_url, key="session_id", value=str(self.state.auth_session_id))
        return sse_url

    async def close(self) -> None:
        await self._client.close()
        self._initialized = False
        self._initialized_connect_seq = None

    async def set_auth_session_id(self, auth_session_id: str | None) -> None:
        """Update the resumable auth session id used for future (re)connects."""
        sid = (auth_session_id or "").strip() or None
        if self.state.auth_session_id == sid:
            return
        self.state.auth_session_id = sid
        # Update the SSE URL for future reconnects. We do not forcefully
        # disconnect here; the current transport may still be mid-login.
        self._client.server_url = self._sse_url()

    async def ensure_initialized(self) -> None:
        async with self._lock:
            # Always connect; McpSseClient reconnects if the SSE stream dropped.
            await self._client.connect()
            if (
                self._initialized
                and self._initialized_connect_seq is not None
                and self._initialized_connect_seq == self._client.connect_seq
            ):
                return
            init = await self._client.initialize()
            self.state.server_info = init.server_info
            self.state.capabilities = init.capabilities
            self._initialized = True
            self._initialized_connect_seq = self._client.connect_seq

    async def tools_list(self) -> dict[str, Any]:
        await self.ensure_initialized()
        res = await self._client.tools_list()
        return dict(res or {}) if isinstance(res, dict) else {"tools": res}

    async def tools_call(self, *, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        await self.ensure_initialized()
        res = await self._client.tools_call(name=name, arguments=arguments)
        return dict(res or {}) if isinstance(res, dict) else {"result": res}


class KiteMcpSessionManager:
    """Process-local session manager.

    We keep a single active session (global/admin) to support the auth flow:
    the user clicks a login link, then subsequent tool calls must reuse the
    same MCP session context (or a resumable auth token).
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._session: KiteMcpSession | None = None

    async def get_session(self, *, server_url: str, auth_session_id: str | None) -> KiteMcpSession:
        server_url2 = (server_url or "").strip().rstrip("/")
        async with self._lock:
            if self._session is None:
                self._session = KiteMcpSession(server_url=server_url2, auth_session_id=auth_session_id)
                return self._session
            if self._session.state.server_url != server_url2:
                try:
                    await self._session.close()
                except Exception:
                    pass
                self._session = KiteMcpSession(server_url=server_url2, auth_session_id=auth_session_id)
                return self._session
            # Keep the existing session when auth_session_id changes to avoid
            # breaking the login flow (authorization may be tied to the
            # underlying MCP transport session). But do update the resumable
            # token so future reconnects do not lose authorization.
            if self._session.state.auth_session_id != auth_session_id:
                await self._session.set_auth_session_id(auth_session_id)
            return self._session

    async def reset(self) -> None:
        async with self._lock:
            if self._session is None:
                return
            try:
                await self._session.close()
            finally:
                self._session = None


kite_mcp_sessions = KiteMcpSessionManager()


__all__ = ["KiteMcpSession", "KiteMcpSessionManager", "kite_mcp_sessions"]
