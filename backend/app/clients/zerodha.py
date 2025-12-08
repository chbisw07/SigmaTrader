from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Protocol

from app.core.config import Settings


class KiteLike(Protocol):
    """Protocol capturing the KiteConnect methods we rely on.

    This allows us to unit test the Zerodha client with a fake implementation
    without requiring real network calls.
    """

    def set_access_token(self, access_token: str) -> None:  # pragma: no cover
        ...

    def place_order(
        self, *args: Any, **kwargs: Any
    ) -> Dict[str, Any]:  # pragma: no cover
        ...

    def orders(self) -> list[Dict[str, Any]]:  # pragma: no cover
        ...

    def order_history(self, order_id: str) -> list[Dict[str, Any]]:  # pragma: no cover
        ...

    def positions(self) -> Dict[str, Any]:  # pragma: no cover
        ...

    def holdings(self) -> List[Dict[str, Any]]:  # pragma: no cover
        ...

    def ltp(self, instruments: list[str]) -> Dict[str, Any]:  # pragma: no cover
        ...

    def place_gtt(
        self,
        trigger_type: str,
        tradingsymbol: str,
        exchange: str,
        trigger_values: List[float],
        last_price: float,
        orders: List[Dict[str, Any]],
    ) -> Dict[str, Any]:  # pragma: no cover
        ...

    def get_gtts(self) -> List[Dict[str, Any]]:  # pragma: no cover
        ...

    def delete_gtt(self, trigger_id: int) -> Dict[str, Any]:  # pragma: no cover
        ...


@dataclass
class ZerodhaOrderResult:
    order_id: str
    raw: Dict[str, Any]


class ZerodhaClient:
    """Thin wrapper around Zerodha KiteConnect client.

    For S05/G01 we only configure the client and expose basic services
    for placing orders and fetching order book / order status. OAuth and
    token storage are handled in later groups.
    """

    def __init__(self, kite: KiteLike) -> None:
        self._kite = kite

    @classmethod
    def from_settings(cls, settings: Settings, access_token: str) -> "ZerodhaClient":
        """Create a ZerodhaClient using API key/secret from settings.

        The caller is responsible for obtaining a valid access_token.
        """

        if not settings.zerodha_api_key:
            raise RuntimeError("Zerodha API key (ST_ZERODHA_API_KEY) not configured.")

        # Import lazily so tests using a fake implementation do not require kiteconnect.
        from kiteconnect import KiteConnect  # type: ignore[import]

        kite = KiteConnect(api_key=settings.zerodha_api_key)
        kite.set_access_token(access_token)
        return cls(kite)

    def place_order(
        self,
        *,
        tradingsymbol: str,
        transaction_type: str,
        quantity: float,
        order_type: str = "MARKET",
        product: str = "MIS",
        price: float | None = None,
        trigger_price: float | None = None,
        variety: str = "regular",
        exchange: str = "NSE",
        **extra: Any,
    ) -> ZerodhaOrderResult:
        """Place a market/limit order via KiteConnect.

        Parameters are intentionally close to KiteConnect's API but constrained
        to SigmaTrader's current use cases.
        """

        params: Dict[str, Any] = {
            "tradingsymbol": tradingsymbol,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "order_type": order_type,
            "product": product,
            "variety": variety,
            "exchange": exchange,
        }
        if price is not None:
            params["price"] = price
        if trigger_price is not None:
            params["trigger_price"] = trigger_price

        params.update(extra)

        response = self._kite.place_order(**params)

        # The real KiteConnect API returns a plain order_id string, while some
        # fake clients used in tests may return a dict-like payload. Handle
        # both shapes defensively so we never assume a `.get` method on a
        # string and leak an AttributeError into the UI.
        if isinstance(response, str):
            order_id = response
            raw: Dict[str, Any] = {"order_id": response}
        else:
            raw = dict(response)
            order_id = str(raw.get("order_id"))

        return ZerodhaOrderResult(order_id=order_id, raw=raw)

    def get_ltp(self, *, exchange: str, tradingsymbol: str) -> float:
        """Return last traded price (LTP) for a single instrument.

        This is a thin wrapper around KiteConnect.ltp, kept here so that
        the rest of the codebase does not depend directly on the third
        party client.
        """

        instrument = f"{exchange}:{tradingsymbol}"
        data = self._kite.ltp([instrument])
        if instrument not in data:
            raise RuntimeError(f"LTP quote for {instrument} not returned by broker.")
        quote = data[instrument]
        # The KiteConnect ltp API returns a dict with an `last_price` key.
        return float(quote["last_price"])

    def get_ltp_bulk(
        self,
        instruments: list[tuple[str, str]],
    ) -> Dict[tuple[str, str], Dict[str, float | None]]:
        """Return LTP and previous close for multiple instruments.

        The input is a list of (exchange, tradingsymbol) pairs. The result
        maps the same pairs to a dict containing:
        - last_price: current traded price
        - prev_close: previous close price when available
        """

        if not instruments:
            return {}

        codes = [f"{exchange}:{symbol}" for exchange, symbol in instruments]
        data = self._kite.ltp(codes)

        result: Dict[tuple[str, str], Dict[str, float | None]] = {}
        for (exchange, symbol), code in zip(instruments, codes, strict=False):
            quote = data.get(code)
            if not quote:
                continue
            last_price = float(quote.get("last_price", 0.0))
            ohlc = quote.get("ohlc") or {}
            close_val = ohlc.get("close")
            prev_close = float(close_val) if close_val is not None else None
            result[(exchange, symbol)] = {
                "last_price": last_price,
                "prev_close": prev_close,
            }
        return result

    def list_orders(self) -> list[Dict[str, Any]]:
        """Return Zerodha order book."""

        return self._kite.orders()

    def get_order_history(self, order_id: str) -> list[Dict[str, Any]]:
        """Return full history for a given order id."""

        return self._kite.order_history(order_id)

    def list_positions(self) -> Dict[str, Any]:
        """Return Zerodha positions payload."""

        return self._kite.positions()

    def list_holdings(self) -> List[Dict[str, Any]]:
        """Return Zerodha holdings list."""

        return self._kite.holdings()

    def margins(self, segment: str | None = None) -> Dict[str, Any]:
        """Return account margin details for the given segment."""

        return self._kite.margins(segment)

    def order_margins(self, params: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return margin/charges preview for the given order list."""

        return self._kite.order_margins(params)

    def place_gtt_single(
        self,
        *,
        tradingsymbol: str,
        exchange: str,
        transaction_type: str,
        quantity: float,
        product: str,
        trigger_price: float,
        order_price: float,
        last_price: float,
    ) -> Dict[str, Any]:
        """Place a single-leg GTT for an equity instrument.

        This is a thin wrapper around KiteConnect.place_gtt with
        trigger_type=\"single\" and a single LIMIT order.
        """

        orders = [
            {
                "transaction_type": transaction_type,
                "quantity": int(quantity),
                "order_type": "LIMIT",
                "product": product,
                "price": float(order_price),
            }
        ]
        trigger_values = [float(trigger_price)]
        return self._kite.place_gtt(
            "single",
            tradingsymbol,
            exchange,
            trigger_values,
            float(last_price),
            orders,
        )

    def list_gtts(self) -> List[Dict[str, Any]]:
        """Return list of existing GTTs."""

        return self._kite.get_gtts()

    def delete_gtt(self, trigger_id: int) -> Dict[str, Any]:
        """Delete a GTT by trigger id."""

        return self._kite.delete_gtt(trigger_id)


__all__ = ["ZerodhaClient", "ZerodhaOrderResult"]
