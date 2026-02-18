from __future__ import annotations

import asyncio

import pytest


def test_mcp_sse_client_missing_h2_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.clients import mcp_sse

    class BoomClient:  # noqa: D401 - test stub
        def __init__(self, *args, **kwargs):  # noqa: ANN001, D401
            if kwargs.get("http2") is True:
                raise ImportError("Using http2=True, but the 'h2' package is not installed.")

    monkeypatch.setattr(mcp_sse.httpx, "AsyncClient", BoomClient)

    with pytest.raises(mcp_sse.McpError) as exc:
        mcp_sse.McpSseClient(server_url="https://mcp.kite.trade/sse", http2=True)

    msg = str(exc.value).lower()
    assert "http/2" in msg or "http2" in msg
    assert "install" in msg


def test_mcp_sse_client_resolves_absolute_endpoint_to_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.clients import mcp_sse

    class FakeResp:
        async def aclose(self) -> None:
            return None

    class FakeStreamCM:
        async def __aenter__(self):  # noqa: ANN001
            return FakeResp()

        async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
            return None

    class FakeHttpxClient:
        def __init__(self, *args, **kwargs):  # noqa: ANN001
            return None

        def stream(self, *args, **kwargs):  # noqa: ANN001
            return FakeStreamCM()

        async def aclose(self) -> None:
            return None

        async def post(self, *args, **kwargs):  # noqa: ANN001
            return None

    async def fake_iter_events(_resp):  # noqa: ANN001
        yield "endpoint", "/message?sessionId=abc"

    monkeypatch.setattr(mcp_sse.httpx, "AsyncClient", FakeHttpxClient)
    monkeypatch.setattr(mcp_sse, "_iter_sse_events", fake_iter_events)

    async def _run() -> None:
        client = mcp_sse.McpSseClient(server_url="https://mcp.kite.trade/sse", timeout_seconds=0.1)
        await client.connect()
        assert client.message_endpoint == "https://mcp.kite.trade/message?sessionId=abc"
        await client.close()

    asyncio.run(_run())
