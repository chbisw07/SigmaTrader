from __future__ import annotations

from datetime import UTC, datetime
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.zerodha import ZerodhaClient
from app.core.config import Settings
from app.core.crypto import decrypt_token
from app.models import BrokerConnection
from app.schemas.ai_trading_manager import BrokerOrder, BrokerPosition, BrokerSnapshot, Quote

from ..broker_adapter import BrokerAdapter, BrokerOrderAck, OrderIntent


class ZerodhaKiteConnectAdapter(BrokerAdapter):
    name = "zerodha_kiteconnect"

    def __init__(self, db: Session, *, settings: Settings, user_id: int | None) -> None:
        self._db = db
        self._settings = settings
        self._user_id = user_id

    def _get_access_token(self) -> str:
        stmt = select(BrokerConnection).where(BrokerConnection.broker_name == "zerodha")
        if self._user_id is not None:
            stmt = stmt.where(BrokerConnection.user_id == self._user_id)
        conn = self._db.execute(stmt).scalars().first()
        if conn is None:
            raise RuntimeError("Zerodha broker connection not found.")
        return decrypt_token(self._settings, conn.access_token_encrypted)

    def _client(self) -> ZerodhaClient:
        token = self._get_access_token()
        return ZerodhaClient.from_settings(self._settings, access_token=token)

    def get_snapshot(self, *, account_id: str) -> BrokerSnapshot:
        now = datetime.now(UTC)
        client = self._client()

        holdings = client.list_holdings()
        pos_payload = client.list_positions() or {}
        orders_payload = client.list_orders()
        margins = client.margins()

        positions: List[BrokerPosition] = []
        for p in (pos_payload.get("net") or []):
            try:
                positions.append(
                    BrokerPosition(
                        symbol=str(p.get("tradingsymbol") or "").strip().upper(),
                        product=str(p.get("product") or "CNC").strip().upper(),
                        qty=float(p.get("quantity") or 0.0),
                        avg_price=float(p.get("average_price") or 0.0) if p.get("average_price") is not None else None,
                    )
                )
            except Exception:
                continue

        orders: List[BrokerOrder] = []
        for o in orders_payload or []:
            try:
                orders.append(
                    BrokerOrder(
                        broker_order_id=str(o.get("order_id") or ""),
                        symbol=str(o.get("tradingsymbol") or "").strip().upper(),
                        side=str(o.get("transaction_type") or "").strip().upper(),  # BUY/SELL
                        product=str(o.get("product") or "CNC").strip().upper(),
                        qty=float(o.get("quantity") or 0.0),
                        order_type=str(o.get("order_type") or "MARKET").strip().upper(),
                        status=str(o.get("status") or "UNKNOWN").strip().upper(),
                    )
                )
            except Exception:
                continue

        return BrokerSnapshot(
            as_of_ts=now,
            account_id=account_id,
            source=self.name,
            holdings=list(holdings or []),
            positions=positions,
            orders=orders,
            margins=dict(margins or {}),
            quotes_cache=[],
        )

    def get_quotes(self, *, account_id: str, symbols: List[str]) -> List[Quote]:
        if not symbols:
            return []
        client = self._client()
        instruments = [("NSE", s) for s in symbols]
        out = client.get_quote_bulk(instruments)
        now = datetime.now(UTC)
        quotes: List[Quote] = []
        for exch, sym in instruments:
            q = out.get((exch, sym))
            if not q:
                continue
            quotes.append(Quote(symbol=str(sym).upper(), last_price=float(q.get("last_price") or 0.0), as_of_ts=now))
        return quotes

    def place_order(self, *, account_id: str, intent: OrderIntent) -> BrokerOrderAck:
        client = self._client()
        result = client.place_order(
            tradingsymbol=intent.symbol,
            transaction_type=str(intent.side).upper(),
            quantity=float(intent.qty),
            order_type=str(intent.order_type).upper(),
            product=str(intent.product).upper(),
            exchange="NSE",
            tag=(intent.correlation_id or "")[:20] or None,
        )
        return BrokerOrderAck(broker_order_id=result.order_id, status="ACK")

    def get_orders(self, *, account_id: str) -> List[BrokerOrder]:
        # Reuse snapshot normalization.
        snap = self.get_snapshot(account_id=account_id)
        return snap.orders
