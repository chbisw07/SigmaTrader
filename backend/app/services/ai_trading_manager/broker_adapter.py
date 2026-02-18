from __future__ import annotations

from dataclasses import dataclass
from typing import List, Protocol

from app.schemas.ai_trading_manager import BrokerOrder, BrokerSnapshot, Quote


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: str  # BUY/SELL
    qty: float
    product: str = "CNC"
    order_type: str = "MARKET"
    limit_price: float | None = None
    correlation_id: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class BrokerOrderAck:
    broker_order_id: str
    status: str = "ACK"


class BrokerAdapter(Protocol):
    name: str

    def get_snapshot(self, *, account_id: str) -> BrokerSnapshot: ...

    def get_quotes(self, *, account_id: str, symbols: List[str]) -> List[Quote]: ...

    def place_order(self, *, account_id: str, intent: OrderIntent) -> BrokerOrderAck: ...

    def get_orders(self, *, account_id: str) -> List[BrokerOrder]: ...

