from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Protocol


@dataclass(frozen=True)
class DiscoveredModel:
    id: str
    label: str
    source: str = "discovered"  # discovered|curated
    raw: Dict[str, Any] | None = None


@dataclass(frozen=True)
class TestResult:
    text: str
    latency_ms: int
    usage: Dict[str, Any] | None = None
    raw_metadata: Dict[str, Any] | None = None


class ProviderClient(Protocol):
    provider_id: str

    def discover_models(self) -> List[DiscoveredModel]: ...

    def run_test(self, *, model: str, prompt: str) -> TestResult: ...


class ProviderError(RuntimeError):
    pass


class ProviderAuthError(ProviderError):
    pass


class ProviderConfigError(ProviderError):
    pass


__all__ = [
    "DiscoveredModel",
    "ProviderAuthError",
    "ProviderClient",
    "ProviderConfigError",
    "ProviderError",
    "TestResult",
]
