from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Protocol

import httpx


JsonGetResult = tuple[bool, int | None, Dict[str, Any] | None, str | None]


@dataclass(frozen=True)
class KiteMcpTestResult:
    ok: bool
    status_code: int | None = None
    error: str | None = None
    used_endpoint: str | None = None
    health: Dict[str, Any] | None = None
    capabilities: Dict[str, Any] | None = None


class KiteMCPClient(Protocol):
    """Minimal MCP client interface used for connectivity tests.

    Phase 1 will replace this with a real MCP transport + tool router. For
    now, we keep the contract small and boring: ping /health and best-effort
    capabilities discovery via HTTP GET endpoints.
    """

    def test_connection(self, *, server_url: str, fetch_capabilities: bool = True) -> KiteMcpTestResult: ...


class HttpKiteMCPClient:
    def __init__(self, *, timeout_seconds: int = 5) -> None:
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _truncate(text: str, limit: int = 300) -> str:
        t = (text or "").strip()
        if len(t) <= limit:
            return t
        return f"{t[:limit]}…"

    @staticmethod
    def _as_dict(value: Any) -> Dict[str, Any] | None:
        if isinstance(value, dict):
            return value
        return None

    def _try_json_get(self, client: httpx.Client, url: str) -> JsonGetResult:
        try:
            resp = client.get(url)
        except Exception as exc:
            return False, None, None, str(exc)

        status = int(resp.status_code)
        if status < 200 or status >= 300:
            # Capture a short body in case it's a useful error.
            body = self._truncate(resp.text)
            return False, status, None, f"HTTP {status}{(': ' + body) if body else ''}"

        try:
            data = resp.json()
        except Exception:
            return True, status, None, None
        return True, status, self._as_dict(data), None

    @staticmethod
    def _endpoints(server_url: str, paths: Iterable[str]) -> Iterable[str]:
        base = (server_url or "").rstrip("/")
        for p in paths:
            p2 = str(p or "").strip()
            if not p2:
                continue
            if not p2.startswith("/"):
                p2 = "/" + p2
            yield f"{base}{p2}"

    def test_connection(self, *, server_url: str, fetch_capabilities: bool = True) -> KiteMcpTestResult:
        base = (server_url or "").strip().rstrip("/")
        if not base:
            return KiteMcpTestResult(ok=False, error="server_url is required.")

        health_paths = ("/health", "/mcp/health", "/api/health")
        caps_paths = ("/capabilities", "/mcp/capabilities", "/tools", "/mcp/tools")

        with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
            health: Optional[Dict[str, Any]] = None
            capabilities: Optional[Dict[str, Any]] = None

            last_err: str | None = None
            last_status: int | None = None
            used: str | None = None

            for url in self._endpoints(base, health_paths):
                ok, status, data, err = self._try_json_get(client, url)
                used = url
                last_status = status
                if ok:
                    health = data
                    last_err = None
                    break
                last_err = err

            if fetch_capabilities:
                for url in self._endpoints(base, caps_paths):
                    ok, status, data, err = self._try_json_get(client, url)
                    used = url
                    last_status = status
                    if ok:
                        capabilities = data
                        last_err = None
                        break
                    last_err = err

            # Connected if any endpoint succeeded.
            ok = health is not None or capabilities is not None
            return KiteMcpTestResult(
                ok=ok,
                status_code=last_status,
                error=None if ok else (last_err or "Unable to reach Kite MCP server."),
                used_endpoint=used,
                health=health,
                capabilities=capabilities,
            )


__all__ = ["HttpKiteMCPClient", "KiteMCPClient", "KiteMcpTestResult"]
