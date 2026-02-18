from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Dict, List, Literal, Optional
from uuid import uuid4

from app.schemas.ai_trading_manager import BrokerSnapshot, Quote

from ..broker_adapter import BrokerAdapter, BrokerOrderAck, OrderIntent


@dataclass
class StubBrokerAdapter(BrokerAdapter):
    """Deterministic stub adapter for Phase 0.

    Modes:
    - mirror: returns empty holdings but preserves any quotes set via constructor
      and produces a consistent snapshot shape.
    - empty: returns an empty snapshot (useful for tests to generate deltas).
    """

    mode: Literal["mirror", "empty"] = "mirror"
    fixed_quotes: Optional[Dict[str, float]] = None
    name: str = "stub"

    def get_snapshot(self, *, account_id: str) -> BrokerSnapshot:
        now = datetime.now(UTC)
        if self.mode == "empty":
            return BrokerSnapshot(as_of_ts=now, account_id=account_id, source="stub")
        quotes_cache = []
        if self.fixed_quotes:
            for sym, px in sorted(self.fixed_quotes.items()):
                quotes_cache.append(Quote(symbol=sym, last_price=float(px), as_of_ts=now))
        return BrokerSnapshot(
            as_of_ts=now,
            account_id=account_id,
            source="stub",
            holdings=[],
            positions=[],
            orders=[],
            margins={},
            quotes_cache=quotes_cache,
        )

    def get_quotes(self, *, account_id: str, symbols: List[str]) -> List[Quote]:
        snap = self.get_snapshot(account_id=account_id)
        by_sym = {q.symbol: q for q in snap.quotes_cache}
        out: List[Quote] = []
        now = datetime.now(UTC)
        for s in symbols:
            if s in by_sym:
                out.append(by_sym[s])
            else:
                # deterministic fallback
                out.append(Quote(symbol=s, last_price=0.0, as_of_ts=now))
        return out

    def place_order(self, *, account_id: str, intent: OrderIntent) -> BrokerOrderAck:
        # Phase 0 never executes real broker orders. Keep a deterministic stub
        # ack shape for tests and dry-run flows.
        return BrokerOrderAck(broker_order_id=f"stub-{uuid4().hex}", status="ACK")

    def get_orders(self, *, account_id: str):
        return []

