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


__all__ = ["ZerodhaClient", "ZerodhaOrderResult"]
