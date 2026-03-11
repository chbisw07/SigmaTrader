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
        if line.startswith(":"):
            # Comment/heartbeat.
            continue
        if line == "":
            if data_lines:
                # SSE spec: default event type is "message" when no explicit
                # `event:` field is present.
                yield (event or "message"), "\n".join(data_lines)
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
        endpoint_required: bool = True,
    ) -> None:
        self.server_url = _normalize_sse_url(server_url)
        self._timeout_seconds = float(timeout_seconds)
        self._endpoint_required = bool(endpoint_required)
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
        self._sse_stream_cm: Any | None = None
        self._reader_task: asyncio.Task | None = None

        self._message_endpoint: str | None = None
        self._http_post_only: bool = False
        self._connect_seq = 0
        self._next_id = 1
        self._pending: dict[int, asyncio.Future] = {}

        self.initialize_result: McpInitializeResult | None = None

    @property
    def connect_seq(self) -> int:
        return int(self._connect_seq)

    @property
    def message_endpoint(self) -> str | None:
        return self._message_endpoint

    @property
    def is_connected(self) -> bool:
        if self._sse_response is None or self._message_endpoint is None:
            return False
        if getattr(self._sse_response, "is_closed", False):
            return False
        if self._reader_task is None or self._reader_task.done():
            return False
        return True

    async def __aenter__(self) -> "McpSseClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        await self.close()

    async def disconnect(self) -> None:
        """Disconnect the SSE transport but keep the underlying HTTP client open."""
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except BaseException:
                pass
            self._reader_task = None

        # Fail pending.
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(McpError("MCP session disconnected."))
        self._pending.clear()

        if self._sse_response is not None:
            try:
                await self._sse_response.aclose()
            except Exception:
                pass
            self._sse_response = None
        if self._sse_stream_cm is not None:
            try:
                await self._sse_stream_cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._sse_stream_cm = None

        self._message_endpoint = None
        self.initialize_result = None

    async def connect(self) -> None:
        if self._http_post_only:
            self._message_endpoint = self.server_url
            self._connect_seq += 1
            return

        # If the SSE stream died (Cloudflare idle timeout, network blip), the
        # reader task completes and we stop receiving responses. Treat that as
        # disconnected and transparently reconnect on the next request.
        if self._sse_response is not None:
            if self.is_connected:
                return
            await self.disconnect()

        # Keep a strong reference to the stream context manager. Discarding it
        # can close the underlying stream unexpectedly (GC/finalizer), which
        # prevents us from receiving the initial `endpoint` event.
        stream_cm = self._client.stream(
            "GET",
            self.server_url,
            headers={"Accept": "text/event-stream"},
        )
        resp = await stream_cm.__aenter__()
        self._sse_stream_cm = stream_cm
        self._sse_response = resp

        if not self._endpoint_required:
            ct = str(resp.headers.get("content-type") or "").lower()
            # Some MCP servers expose an HTTP JSON-RPC endpoint (POST) and do
            # not support SSE (GET) at the same URL (e.g., return 405 on GET).
            if resp.status_code != 200 or "text/event-stream" not in ct:
                self._http_post_only = True
                self._message_endpoint = self.server_url
                self._connect_seq += 1
                try:
                    await resp.aclose()
                except Exception:
                    pass
                try:
                    await stream_cm.__aexit__(None, None, None)
                except Exception:
                    pass
                self._sse_response = None
                self._sse_stream_cm = None
                self._reader_task = None
                return

        endpoint_fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()

        async def _reader() -> None:
            try:
                async for ev, data in _iter_sse_events(resp):
                    if not endpoint_fut.done():
                        # Kite-style: `event: endpoint` with a relative POST endpoint.
                        if (ev or "").lower() == "endpoint":
                            endpoint_fut.set_result(data.strip())
                            continue
                        # Some servers may emit the endpoint as a default "message"
                        # event (no explicit `event:` field).
                        if (ev or "").lower() == "message":
                            d = (data or "").strip()
                            if d.startswith("/") or "sessionId=" in d or "session_id=" in d:
                                endpoint_fut.set_result(d)
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
            # Some remote MCP servers do not emit an explicit `endpoint` event.
            # When endpoint isn't required, keep this timeout short so requests
            # don't block the API.
            endpoint_timeout = max(0.5, min(10.0, self._timeout_seconds))
            if not self._endpoint_required:
                endpoint_timeout = min(endpoint_timeout, 1.0)
            endpoint = await asyncio.wait_for(endpoint_fut, timeout=endpoint_timeout)
        except Exception as exc:
            if self._endpoint_required:
                await self.disconnect()
                raise McpError("Failed to establish MCP SSE session.") from exc
            # Fallback: treat the SSE URL itself as the message endpoint.
            endpoint = self.server_url

        # Resolve relative endpoint against server origin.
        if endpoint.startswith("/"):
            # Absolute-path endpoint (origin-root).
            self._message_endpoint = urljoin(self.server_url + "/", endpoint)
        else:
            # Prefer joining against the SSE URL so relative paths like
            # `message?sessionId=...` resolve correctly.
            self._message_endpoint = urljoin(self.server_url + "/", endpoint)
        self._connect_seq += 1

    async def close(self) -> None:
        await self.disconnect()

        if not self._external_client:
            await self._client.aclose()

    async def ensure_initialized(self) -> None:
        await self.connect()
        if self.initialize_result is None:
            await self.initialize()

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
        # Always ensure the SSE transport is connected; it may have dropped
        # silently while the process stayed alive.
        await self.connect()
        if self._message_endpoint is None:
            raise McpError("MCP session is not connected.")

        rid = self._alloc_id()
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut

        payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            payload["params"] = params

        accept_hdr = {"Accept": "application/json, text/event-stream"}

        if self._http_post_only:
            # POST-only mode: the server may respond with:
            # - application/json JSON-RPC body (sync)
            # - text/event-stream (SSE) containing the JSON-RPC response
            async def _post_only() -> Any:
                async with self._client.stream(
                    "POST",
                    self._message_endpoint,
                    json=payload,
                    headers=accept_hdr,
                ) as post_resp:
                    ct = str(post_resp.headers.get("content-type") or "").lower()
                    if post_resp.status_code >= 400:
                        body = ""
                        try:
                            body = (await post_resp.aread()).decode("utf-8", errors="replace")
                        except Exception:
                            body = ""
                        raise McpError(f"MCP POST failed ({post_resp.status_code}){': ' + body if body else ''}")

                    if "text/event-stream" in ct:
                        async for ev, data in _iter_sse_events(post_resp):
                            if (ev or "").lower() != "message":
                                continue
                            try:
                                obj = json.loads(data)
                            except Exception:
                                continue
                            if isinstance(obj, dict) and obj.get("id") == rid:
                                if obj.get("error"):
                                    raise McpError(str(obj["error"]))
                                return obj.get("result")
                        raise McpTimeoutError(f"MCP request timed out: {method}")

                    # Non-SSE response: try JSON first, then raw text.
                    raw = await post_resp.aread()
                    try:
                        obj_direct = json.loads(raw.decode("utf-8", errors="replace")) if raw else None
                    except Exception:
                        obj_direct = None
                    if isinstance(obj_direct, dict):
                        if obj_direct.get("id") == rid and (obj_direct.get("result") is not None or obj_direct.get("error")):
                            if obj_direct.get("error"):
                                raise McpError(str(obj_direct["error"]))
                            return obj_direct.get("result")
                        if obj_direct.get("result") is not None and obj_direct.get("id") in (rid, None):
                            return obj_direct.get("result")
                    return {"raw": raw.decode("utf-8", errors="replace") if raw else ""}

            try:
                res = await asyncio.wait_for(_post_only(), timeout=float(timeout_seconds or self._timeout_seconds))
                self._pending.pop(rid, None)
                return res
            except Exception:
                self._pending.pop(rid, None)
                raise

        # SSE session mode: servers typically ACK with HTTP 202 and send the
        # response on the SSE `message` stream.
        post_resp = await self._client.post(self._message_endpoint, json=payload, headers=accept_hdr)
        if post_resp.status_code >= 400:
            body = ""
            try:
                body = post_resp.text
            except Exception:
                body = ""
            self._pending.pop(rid, None)
            raise McpError(f"MCP POST failed ({post_resp.status_code}){': ' + body if body else ''}")

        # Some servers return JSON-RPC responses directly even in SSE mode.
        obj_direct: Any | None = None
        try:
            if post_resp.content and "application/json" in str(post_resp.headers.get("content-type") or "").lower():
                obj_direct = post_resp.json()
        except Exception:
            obj_direct = None
        if isinstance(obj_direct, dict):
            if obj_direct.get("id") == rid and (obj_direct.get("result") is not None or obj_direct.get("error")):
                self._pending.pop(rid, None)
                if obj_direct.get("error"):
                    raise McpError(str(obj_direct["error"]))
                return obj_direct.get("result")

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
