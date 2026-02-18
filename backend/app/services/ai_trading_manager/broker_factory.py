from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings

from .broker_adapter import BrokerAdapter
from .brokers.stub import StubBrokerAdapter


def get_broker_adapter(
    db: Session,
    *,
    settings: Settings,
    user_id: int | None,
) -> BrokerAdapter:
    # Phase 0 always uses stub. In Phase 1+, the kite_mcp_enabled flag selects
    # a broker-truth adapter. Until the real Kite MCP endpoints are available,
    # this is backed by the existing Zerodha KiteConnect integration.
    if not settings.kite_mcp_enabled:
        return StubBrokerAdapter(mode="mirror")

    broker = (settings.ai_broker_name or "zerodha").strip().lower()
    if broker == "angelone":
        from .brokers.angelone_smartapi import AngelOneSmartApiAdapter

        try:
            return AngelOneSmartApiAdapter(db, settings=settings, user_id=user_id)
        except Exception:
            return StubBrokerAdapter(mode="mirror")

    from .brokers.zerodha_kiteconnect import ZerodhaKiteConnectAdapter

    try:
        return ZerodhaKiteConnectAdapter(db, settings=settings, user_id=user_id)
    except Exception:
        # Degrade to stub so Phase 0/1 UI can still function when broker is
        # not connected. Execution endpoints will remain gated separately.
        return StubBrokerAdapter(mode="mirror")
