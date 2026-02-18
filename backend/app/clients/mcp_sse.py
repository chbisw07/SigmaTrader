from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict
from urllib.parse import urljoin, urlparse

import httpx


class McpError(RuntimeError):
    pass


class McpTimeoutError(McpError):
    pass


@dataclass(frozen=True)
class McpInitializeResult:
    protocol_version: str
    server_info: Dict[str, Any]
    capabilities: Dict[str, Any]


def _normalize_sse_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        raise ValueError("server_url is required.")
    p = urlparse(u)
    if p.scheme not in {"http", "https"} or not p.netloc:
        raise ValueError("server_url must be a valid http(s) URL.")
    return u.rstrip("/")


async def _iter_sse_events(resp: httpx.Response) -> AsyncIterator[tuple[str, str]]:
    """Parse an SSE response into (event, data) tuples."""

    event: str | None = None
    data_lines: list[str] = []
    async for line in resp.aiter_lines():
        if line == "":
            if event is not None:
                yield event, "\n".join(data_lines)
            event = None
            data_lines = []
            continue
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
            continue
        if line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())
            continue
        # Ignore other SSE fields (id, retry, comments).


class McpSseClient:
    """MCP client over SSE + message POST endpoint (HTTP transport).

    Transport pattern (observed from Kite MCP):
    - Client GETs {server_url} (SSE). Server emits `event: endpoint` with
      a relative message endpoint containing sessionId query param.
    - Client POSTs JSON-RPC messages to that endpoint.
    - Server emits JSON-RPC responses via SSE `event: message`.

    IMPORTANT: For Kite MCP behind Cloudflare, this requires HTTP/2
    multiplexing so POST requests route to the same backend instance as the
    SSE stream. We therefore use httpx with http2=True by default.
    """

    def __init__(
        self,
        *,
        server_url: str,
        client: httpx.AsyncClient | None = None,
        http2: bool = True,
        timeout_seconds: float = 30,
    ) -> None:
        self.server_url = _normalize_sse_url(server_url)
        self._timeout_seconds = float(timeout_seconds)
        self._external_client = client is not None
        if client is not None:
            self._client = client
        else:
            try:
                self._client = httpx.AsyncClient(
                    timeout=timeout_seconds,
                    follow_redirects=True,
                    http2=bool(http2),
                )
            except ImportError as exc:
                # httpx raises ImportError when http2=True but h2 isn't installed.
                if http2:
                    raise McpError(
                        "HTTP/2 support is required for Kite MCP (SSE + message POST session affinity). "
                        "Install backend dependencies: `pip install -r backend/requirements.txt` "
                        "(or `pip install 'httpx[http2]'`)."
                    ) from exc
                raise

        self._sse_response: httpx.Response | None = None
        self._reader_task: asyncio.Task | None = None

        self._message_endpoint: str | None = None
        self._next_id = 1
        self._pending: dict[int, asyncio.Future] = {}

        self.initialize_result: McpInitializeResult | None = None

    @property
    def message_endpoint(self) -> str | None:
        return self._message_endpoint

    async def __aenter__(self) -> "McpSseClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        await self.close()

    async def connect(self) -> None:
        if self._sse_response is not None:
            return

        resp = await self._client.stream(
            "GET",
            self.server_url,
            headers={"Accept": "text/event-stream"},
        ).__aenter__()
        self._sse_response = resp

        endpoint_fut: asyncio.Future[str] = asyncio.get_event_loop().create_future()

        async def _reader() -> None:
            try:
                async for ev, data in _iter_sse_events(resp):
                    if ev == "endpoint" and not endpoint_fut.done():
                        endpoint_fut.set_result(data.strip())
                        continue
                    if ev != "message":
                        continue
                    try:
                        obj = json.loads(data)
                    except Exception:
                        continue
                    msg_id = obj.get("id")
                    if isinstance(msg_id, int) and msg_id in self._pending:
                        fut = self._pending.pop(msg_id)
                        if not fut.done():
                            fut.set_result(obj)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Fail any pending requests.
                for fut in list(self._pending.values()):
                    if not fut.done():
                        fut.set_exception(McpError(str(exc)))
                self._pending.clear()

        self._reader_task = asyncio.create_task(_reader())

        try:
            endpoint = await asyncio.wait_for(endpoint_fut, timeout=5)
        except Exception as exc:
            raise McpError("Failed to establish MCP SSE session.") from exc

        # Resolve relative endpoint against server origin.
        if endpoint.startswith("/"):
            self._message_endpoint = urljoin(self.server_url + "/", endpoint.lstrip("/"))
        else:
            self._message_endpoint = endpoint

    async def close(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except Exception:
                pass
            self._reader_task = None

        # Fail pending.
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(McpError("MCP session closed."))
        self._pending.clear()

        if self._sse_response is not None:
            try:
                await self._sse_response.aclose()
            except Exception:
                pass
            self._sse_response = None

        if not self._external_client:
            await self._client.aclose()

    def _alloc_id(self) -> int:
        rid = int(self._next_id)
        self._next_id += 1
        return rid

    async def request(
        self,
        *,
        method: str,
        params: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> Any:
        if self._message_endpoint is None:
            raise McpError("MCP session is not connected.")

        rid = self._alloc_id()
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[rid] = fut

        payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            payload["params"] = params

        # MCP servers typically acknowledge with HTTP 202 and send the response on SSE.
        await self._client.post(self._message_endpoint, json=payload)

        try:
            obj = await asyncio.wait_for(
                fut,
                timeout=float(timeout_seconds or self._timeout_seconds),
            )
        except asyncio.TimeoutError as exc:
            self._pending.pop(rid, None)
            raise McpTimeoutError(f"MCP request timed out: {method}") from exc

        if not isinstance(obj, dict):
            raise McpError("Invalid MCP response.")
        if obj.get("error"):
            raise McpError(str(obj["error"]))
        return obj.get("result")

    async def initialize(self) -> McpInitializeResult:
        result = await self.request(
            method="initialize",
            params={
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "SigmaTrader", "version": "0.1.0"},
                "capabilities": {},
            },
        )
        if not isinstance(result, dict):
            raise McpError("Invalid initialize result.")
        init = McpInitializeResult(
            protocol_version=str(result.get("protocolVersion") or ""),
            server_info=dict(result.get("serverInfo") or {}),
            capabilities=dict(result.get("capabilities") or {}),
        )
        self.initialize_result = init
        return init

    async def tools_list(self) -> dict[str, Any]:
        return await self.request(method="tools/list", params={})

    async def tools_call(self, *, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return await self.request(method="tools/call", params={"name": name, "arguments": arguments})


__all__ = [
    "McpError",
    "McpInitializeResult",
    "McpSseClient",
    "McpTimeoutError",
]
