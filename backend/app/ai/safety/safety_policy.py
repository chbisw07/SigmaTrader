from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.core.config import Settings
from app.schemas.ai_provider import AiActiveConfig
from app.services.ai.provider_registry import get_provider


class SharingMode(str, Enum):
    SAFE_SUMMARIES_ONLY = "SAFE_SUMMARIES_ONLY"
    LOCAL_DEEP_CONTEXT = "LOCAL_DEEP_CONTEXT"  # future; not enabled by default


@dataclass(frozen=True)
class SafetyPolicy:
    mode: SharingMode
    is_remote_provider: bool
    pii_safe_mode_enabled: bool


def get_sharing_mode(settings: Settings, cfg: AiActiveConfig) -> SafetyPolicy:
    """
    Decide the data sharing mode for the current provider.

    Product contract:
    - Remote providers MUST receive safe summaries only (never raw broker payloads),
      regardless of UI toggles.
    - Local providers default to safe summaries only (future: optional deep context).
    """
    provider_id = (cfg.provider or "").strip().lower()
    info = get_provider(provider_id)
    kind = (info.kind if info is not None else "remote").strip().lower()
    is_remote = kind == "remote"

    # For now, local deep context is future-only and intentionally disabled.
    mode = SharingMode.SAFE_SUMMARIES_ONLY

    # "Do not send PII" is treated as a hard contract that enables strict veto behavior.
    pii_safe = bool(cfg.do_not_send_pii)

    _ = settings  # reserved for future knobs
    return SafetyPolicy(mode=mode, is_remote_provider=is_remote, pii_safe_mode_enabled=pii_safe)


__all__ = ["SafetyPolicy", "SharingMode", "get_sharing_mode"]

