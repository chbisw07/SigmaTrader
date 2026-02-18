from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    label: str
    kind: str  # remote|local
    requires_api_key: bool
    supports_base_url: bool
    default_base_url: str | None = None
    supports_model_discovery: bool = True
    supports_test: bool = True


_PROVIDERS: Dict[str, ProviderInfo] = {
    "openai": ProviderInfo(
        id="openai",
        label="OpenAI",
        kind="remote",
        requires_api_key=True,
        supports_base_url=False,
        default_base_url=None,
    ),
    "google": ProviderInfo(
        id="google",
        label="Google (Gemini)",
        kind="remote",
        requires_api_key=True,
        supports_base_url=False,
        default_base_url=None,
    ),
    "local_ollama": ProviderInfo(
        id="local_ollama",
        label="Ollama (local)",
        kind="local",
        requires_api_key=False,
        supports_base_url=True,
        default_base_url="http://localhost:11434",
    ),
    "local_lmstudio": ProviderInfo(
        id="local_lmstudio",
        label="LM Studio (local)",
        kind="local",
        requires_api_key=False,
        supports_base_url=True,
        default_base_url="http://localhost:1234/v1",
    ),
    # Supported as "addable" later; not wired in this change-set.
    "anthropic": ProviderInfo(
        id="anthropic",
        label="Anthropic (coming soon)",
        kind="remote",
        requires_api_key=True,
        supports_base_url=False,
        default_base_url=None,
        supports_model_discovery=False,
        supports_test=False,
    ),
}


def list_providers() -> List[ProviderInfo]:
    return list(_PROVIDERS.values())


def get_provider(provider_id: str) -> Optional[ProviderInfo]:
    key = (provider_id or "").strip().lower()
    return _PROVIDERS.get(key)


__all__ = ["ProviderInfo", "get_provider", "list_providers"]

