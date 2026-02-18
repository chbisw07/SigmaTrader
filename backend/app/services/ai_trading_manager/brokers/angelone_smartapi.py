from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.angelone import AngelOneClient, AngelOneSession
from app.core.config import Settings
from app.core.crypto import decrypt_token
from app.models import BrokerConnection
from app.schemas.ai_trading_manager import BrokerOrder, BrokerPosition, BrokerSnapshot, Quote
from app.services.broker_instruments import resolve_broker_symbol_and_token
from app.services.broker_secrets import get_broker_secret

from ..broker_adapter import BrokerAdapter, BrokerOrderAck, OrderIntent


class AngelOneSmartApiAdapter(BrokerAdapter):
    name = "angelone_smartapi"

    def __init__(self, db: Session, *, settings: Settings, user_id: int | None) -> None:
        self._db = db
        self._settings = settings
        self._user_id = user_id

    def _get_session(self) -> AngelOneSession:
        if self._user_id is None:
            raise RuntimeError("AngelOne broker adapter requires a user id.")
        conn = (
            self._db.execute(
                select(BrokerConnection)
                .where(
                    BrokerConnection.broker_name == "angelone",
                    BrokerConnection.user_id == self._user_id,
                )
                .order_by(BrokerConnection.updated_at.desc())
            )
            .scalars()
            .first()
        )
        if conn is None:
            raise RuntimeError("AngelOne broker connection not found.")
        raw = decrypt_token(self._settings, conn.access_token_encrypted)
        parsed = json.loads(raw) if raw else {}
        jwt = str(parsed.get("jwt_token") or "")
        if not jwt:
            raise RuntimeError("AngelOne session is missing jwt_token.")
        return AngelOneSession(
            jwt_token=jwt,
            refresh_token=str(parsed.get("refresh_token") or "") or None,
            feed_token=str(parsed.get("feed_token") or "") or None,
            client_code=str(parsed.get("client_code") or "") or None,
        )

    def _client(self) -> AngelOneClient:
        if self._user_id is None:
            raise RuntimeError("AngelOne broker adapter requires a user id.")
        api_key = get_broker_secret(self._db, self._settings, "angelone", "api_key", user_id=self._user_id)
        if not api_key:
            raise RuntimeError("AngelOne API key is not configured.")
        return AngelOneClient(api_key=api_key, session=self._get_session())

    def get_snapshot(self, *, account_id: str) -> BrokerSnapshot:
        now = datetime.now(UTC)
        client = self._client()
        try:
            holdings = client.list_holdings()
            positions_payload = client.list_positions()
            orders_payload = client.list_orders()
        finally:
            client.close()

        positions: List[BrokerPosition] = []
        for p in positions_payload or []:
            try:
                sym = str(p.get("tradingsymbol") or p.get("symbol") or "").strip().upper()
                if not sym:
                    continue
                product = str(p.get("producttype") or p.get("product") or "CNC").strip().upper()
                qty_raw = p.get("netqty") or p.get("netQty") or p.get("qty") or p.get("quantity") or 0
                avg_raw = p.get("avgnetprice") or p.get("averageprice") or p.get("avgPrice")
                positions.append(
                    BrokerPosition(
                        symbol=sym,
                        product=product,
                        qty=float(qty_raw or 0.0),
                        avg_price=float(avg_raw) if avg_raw is not None else None,
                    )
                )
            except Exception:
                continue

        orders: List[BrokerOrder] = []
        for o in orders_payload or []:
            try:
                sym = str(o.get("tradingsymbol") or o.get("symbol") or "").strip().upper()
                if not sym:
                    continue
                orders.append(
                    BrokerOrder(
                        broker_order_id=str(o.get("orderid") or o.get("orderId") or o.get("order_id") or ""),
                        symbol=sym,
                        side=str(o.get("transactiontype") or o.get("transactionType") or "").strip().upper(),
                        product=str(o.get("producttype") or o.get("product") or "CNC").strip().upper(),
                        qty=float(o.get("quantity") or 0.0),
                        order_type=str(o.get("ordertype") or o.get("orderType") or "MARKET").strip().upper(),
                        status=str(o.get("orderstatus") or o.get("status") or "UNKNOWN").strip().upper(),
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
            margins={},
            quotes_cache=[],
        )

    def get_quotes(self, *, account_id: str, symbols: List[str]) -> List[Quote]:
        symbols2 = [str(s).strip().upper() for s in symbols if str(s).strip()]
        if not symbols2:
            return []
        client = self._client()
        now = datetime.now(UTC)
        out: List[Quote] = []
        try:
            for sym in symbols2:
                resolved = resolve_broker_symbol_and_token(
                    self._db,
                    broker_name="angelone",
                    exchange="NSE",
                    symbol=sym,
                )
                if resolved is None:
                    out.append(Quote(symbol=sym, last_price=0.0, as_of_ts=now))
                    continue
                broker_symbol, token = resolved
                ltp = client.get_ltp(exchange="NSE", tradingsymbol=broker_symbol, symboltoken=token)
                out.append(Quote(symbol=sym, last_price=float(ltp or 0.0), as_of_ts=now))
        finally:
            client.close()
        return out

    def place_order(self, *, account_id: str, intent: OrderIntent) -> BrokerOrderAck:
        if self._user_id is None:
            raise RuntimeError("AngelOne broker adapter requires a user id.")
        resolved = resolve_broker_symbol_and_token(
            self._db,
            broker_name="angelone",
            exchange="NSE",
            symbol=intent.symbol,
        )
        if resolved is None:
            raise RuntimeError(f"AngelOne instrument mapping missing for NSE:{intent.symbol}.")
        broker_symbol, token = resolved
        client = self._client()
        try:
            res = client.place_order(
                exchange="NSE",
                tradingsymbol=broker_symbol,
                symboltoken=token,
                transactiontype=str(intent.side).upper(),
                quantity=int(max(float(intent.qty), 0.0)),
                ordertype=str(intent.order_type).upper(),
                producttype=str(intent.product).upper(),
            )
        finally:
            client.close()
        return BrokerOrderAck(broker_order_id=res.order_id, status="ACK")

    def get_orders(self, *, account_id: str) -> List[BrokerOrder]:
        snap = self.get_snapshot(account_id=account_id)
        return snap.orders

