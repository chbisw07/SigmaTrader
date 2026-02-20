from __future__ import annotations

import time
from typing import Any, Dict, List

import httpx

from .base import DiscoveredModel, ProviderError, TestResult


class OllamaClient:
    provider_id = "local_ollama"

    def __init__(self, *, base_url: str, timeout_seconds: int = 30) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self._client = httpx.Client(timeout=timeout_seconds, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    def discover_models(self) -> List[DiscoveredModel]:
        url = f"{self.base_url}/api/tags"
        try:
            resp = self._client.get(url, headers={"Accept": "application/json"})
        except Exception as exc:
            raise ProviderError(str(exc)) from exc
        if resp.status_code >= 400:
            raise ProviderError(f"HTTP {resp.status_code}: {resp.text}")
        payload = resp.json()
        rows = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return []
        out: List[DiscoveredModel] = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            name = str(r.get("name") or "").strip()
            if not name:
                continue
            out.append(DiscoveredModel(id=name, label=name, raw=r))
        out.sort(key=lambda m: m.id)
        return out

    def run_test(self, *, model: str, prompt: str, temperature: float | None = None) -> TestResult:
        url = f"{self.base_url}/api/generate"
        body: Dict[str, Any] = {"model": model, "prompt": prompt, "stream": False}
        if temperature is not None:
            body["options"] = {"temperature": float(temperature)}
        t0 = time.perf_counter()
        try:
            resp = self._client.post(
                url,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                json=body,
            )
        except Exception as exc:
            raise ProviderError(str(exc)) from exc
        latency_ms = int((time.perf_counter() - t0) * 1000)
        if resp.status_code >= 400:
            raise ProviderError(f"HTTP {resp.status_code}: {resp.text}")
        payload = resp.json()
        text = str(payload.get("response") or "") if isinstance(payload, dict) else ""
        usage: Dict[str, Any] = {}
        if isinstance(payload, dict):
            # Best-effort token-like counters.
            usage = {
                "input_tokens": payload.get("prompt_eval_count"),
                "output_tokens": payload.get("eval_count"),
                "total_tokens": None,
            }
        return TestResult(
            text=text.strip(),
            latency_ms=latency_ms,
            usage=usage,
            raw_metadata={"status_code": resp.status_code},
        )


__all__ = ["OllamaClient"]
