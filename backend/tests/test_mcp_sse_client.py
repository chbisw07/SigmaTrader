from __future__ import annotations

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

