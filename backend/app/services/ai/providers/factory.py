from __future__ import annotations

from app.services.ai.provider_registry import get_provider

from .base import ProviderClient, ProviderConfigError
from .google_gemini import GoogleGeminiClient
from .ollama import OllamaClient
from .openai import OpenAIClient
from .openai_compatible import OpenAICompatibleClient


def build_provider_client(
    *,
    provider_id: str,
    api_key: str | None,
    base_url: str | None,
) -> ProviderClient:
    pid = (provider_id or "").strip().lower()
    info = get_provider(pid)
    if info is None:
        raise ProviderConfigError("Unsupported provider.")

    if pid == "openai":
        if not api_key:
            raise ProviderConfigError("OpenAI API key is required.")
        return OpenAIClient(api_key=api_key)

    if pid == "google":
        if not api_key:
            raise ProviderConfigError("Google API key is required.")
        return GoogleGeminiClient(api_key=api_key)

    if pid == "local_ollama":
        if not base_url:
            raise ProviderConfigError("base_url is required for Ollama.")
        return OllamaClient(base_url=base_url)

    if pid == "local_lmstudio":
        if not base_url:
            raise ProviderConfigError("base_url is required for LM Studio.")
        # LM Studio is typically OpenAI-compatible; key optional.
        return OpenAICompatibleClient(base_url=base_url, api_key=api_key)

    raise ProviderConfigError("Provider is not implemented yet.")


__all__ = ["build_provider_client"]
