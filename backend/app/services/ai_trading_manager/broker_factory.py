from __future__ import annotations

from app.core.config import Settings

from .broker_adapter import BrokerAdapter
from .brokers.stub import StubBrokerAdapter


def get_broker_adapter(settings: Settings) -> BrokerAdapter:
    # Phase 0: only stub adapter is implemented; Kite MCP arrives in Phase 1.
    # Keep selection logic in place so Phase 0 merges are wiring-complete.
    if settings.kite_mcp_enabled:
        return StubBrokerAdapter(mode="mirror")
    return StubBrokerAdapter(mode="mirror")

