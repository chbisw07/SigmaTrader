from __future__ import annotations

import time
from typing import Any, Dict, List

import httpx

from .base import DiscoveredModel, ProviderAuthError, ProviderError, TestResult


class OpenAICompatibleClient:
    """OpenAI-compatible HTTP API client (LM Studio, custom gateways).

    Expects base_url to include "/v1" (e.g. http://localhost:1234/v1).
    """

    provider_id = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = (api_key or "").strip() or None
        self._client = httpx.Client(timeout=timeout_seconds, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _url(self, path: str) -> str:
        p = str(path or "").strip()
        if not p.startswith("/"):
            p = "/" + p
        return f"{self.base_url}{p}"

    def discover_models(self) -> List[DiscoveredModel]:
        url = self._url("/models")
        try:
            resp = self._client.get(url, headers=self._headers())
        except Exception as exc:
            raise ProviderError(str(exc)) from exc

        if resp.status_code in {401, 403}:
            raise ProviderAuthError("Unauthorized.")
        if resp.status_code >= 400:
            raise ProviderError(f"HTTP {resp.status_code}: {resp.text}")

        payload = resp.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            return []

        out: List[DiscoveredModel] = []
        for row in data:
            if not isinstance(row, dict):
                continue
            mid = str(row.get("id") or "").strip()
            if not mid:
                continue
            out.append(DiscoveredModel(id=mid, label=mid, raw=row))
        out.sort(key=lambda m: m.id)
        return out

    def run_test(self, *, model: str, prompt: str) -> TestResult:
        url = self._url("/chat/completions")
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }
        t0 = time.perf_counter()
        try:
            resp = self._client.post(url, headers=self._headers(), json=body)
        except Exception as exc:
            raise ProviderError(str(exc)) from exc
        latency_ms = int((time.perf_counter() - t0) * 1000)

        if resp.status_code in {401, 403}:
            raise ProviderAuthError("Unauthorized.")
        if resp.status_code >= 400:
            raise ProviderError(f"HTTP {resp.status_code}: {resp.text}")

        payload = resp.json()
        text = ""
        usage: Dict[str, Any] = {}
        if isinstance(payload, dict):
            choices = payload.get("choices")
            if isinstance(choices, list) and choices:
                msg = choices[0].get("message") if isinstance(choices[0], dict) else None
                if isinstance(msg, dict):
                    text = str(msg.get("content") or "")
            u = payload.get("usage")
            if isinstance(u, dict):
                usage = {
                    "input_tokens": u.get("prompt_tokens"),
                    "output_tokens": u.get("completion_tokens"),
                    "total_tokens": u.get("total_tokens"),
                }
        return TestResult(
            text=text.strip(),
            latency_ms=latency_ms,
            usage=usage,
            raw_metadata={"status_code": resp.status_code},
        )


__all__ = ["OpenAICompatibleClient"]
