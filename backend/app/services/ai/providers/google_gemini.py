from __future__ import annotations

import time
from typing import Any, Dict, List

import httpx

from .base import DiscoveredModel, ProviderAuthError, ProviderError, TestResult


class GoogleGeminiClient:
    provider_id = "google"

    def __init__(self, *, api_key: str, timeout_seconds: int = 30) -> None:
        self.api_key = (api_key or "").strip()
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self._client = httpx.Client(timeout=timeout_seconds, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    def _url(self, path: str) -> str:
        p = str(path or "").strip()
        if not p.startswith("/"):
            p = "/" + p
        return f"{self.base_url}{p}?key={self.api_key}"

    @staticmethod
    def _normalize_model_id(model: str) -> str:
        m = (model or "").strip()
        if not m:
            return ""
        if m.startswith("models/"):
            return m
        return f"models/{m}"

    def discover_models(self) -> List[DiscoveredModel]:
        url = self._url("/models")
        try:
            resp = self._client.get(url, headers={"Accept": "application/json"})
        except Exception as exc:
            raise ProviderError(str(exc)) from exc

        if resp.status_code in {401, 403}:
            raise ProviderAuthError("Unauthorized.")
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
            short = name.split("/", 1)[1] if name.startswith("models/") and "/" in name else name
            label = str(r.get("displayName") or short).strip() or short
            out.append(DiscoveredModel(id=short, label=label, raw=r))
        out.sort(key=lambda m: m.id)
        return out

    def run_test(self, *, model: str, prompt: str) -> TestResult:
        model_name = self._normalize_model_id(model)
        if not model_name:
            raise ProviderError("model is required.")
        url = self._url(f"/{model_name}:generateContent")
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}

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

        if resp.status_code in {401, 403}:
            raise ProviderAuthError("Unauthorized.")
        if resp.status_code >= 400:
            raise ProviderError(f"HTTP {resp.status_code}: {resp.text}")

        payload = resp.json()
        text = ""
        usage: Dict[str, Any] = {}
        if isinstance(payload, dict):
            cands = payload.get("candidates")
            if isinstance(cands, list) and cands:
                cand0 = cands[0] if isinstance(cands[0], dict) else None
                content = cand0.get("content") if isinstance(cand0, dict) else None
                parts = content.get("parts") if isinstance(content, dict) else None
                if isinstance(parts, list) and parts and isinstance(parts[0], dict):
                    text = str(parts[0].get("text") or "")
            um = payload.get("usageMetadata")
            if isinstance(um, dict):
                usage = {
                    "input_tokens": um.get("promptTokenCount"),
                    "output_tokens": um.get("candidatesTokenCount"),
                    "total_tokens": um.get("totalTokenCount"),
                }

        return TestResult(
            text=text.strip(),
            latency_ms=latency_ms,
            usage=usage,
            raw_metadata={"status_code": resp.status_code},
        )


__all__ = ["GoogleGeminiClient"]
