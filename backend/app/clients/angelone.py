from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import httpx


@dataclass
class AngelOneSession:
    jwt_token: str
    refresh_token: str | None = None
    feed_token: str | None = None
    client_code: str | None = None


@dataclass
class AngelOneOrderResult:
    order_id: str
    raw: Dict[str, Any]


class AngelOneClient:
    """Minimal SmartAPI (AngelOne) client using HTTP calls.

    This avoids a hard dependency on smartapi-python so tests and lightweight
    environments can still import the backend without installing extra wheels.
    """

    def __init__(
        self,
        *,
        api_key: str,
        session: AngelOneSession,
        base_url: str = "https://apiconnect.angelone.in",
        timeout_seconds: int = 30,
    ) -> None:
        self.api_key = api_key
        self.session = session
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        self._client.close()

    def _headers(self) -> dict[str, str]:
        # SmartAPI requires several headers. We use conservative defaults.
        h = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-PrivateKey": self.api_key,
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress": "00:00:00:00:00:00",
        }
        if self.session.jwt_token:
            h["Authorization"] = f"Bearer {self.session.jwt_token}"
        return h

    def _request(self, method: str, path: str, *, json_body: Any | None = None) -> Any:
        url = f"{self.base_url}{path}"
        resp = self._client.request(
            method,
            url,
            headers=self._headers(),
            json=json_body,
        )
        try:
            data = resp.json()
        except Exception:
            resp.raise_for_status()
            raise

        # SmartAPI returns 200 with status=false on failures.
        if resp.status_code >= 400:
            raise RuntimeError(data.get("message") or data)
        if isinstance(data, dict) and data.get("status") is False:
            raise RuntimeError(data.get("message") or data.get("errorcode") or data)
        return data

    @classmethod
    def login(
        cls,
        *,
        api_key: str,
        client_code: str,
        password: str,
        totp: str,
        base_url: str = "https://apiconnect.angelone.in",
        timeout_seconds: int = 30,
    ) -> AngelOneSession:
        payload = {"clientcode": client_code, "password": password, "totp": totp}
        with httpx.Client(timeout=timeout_seconds) as client:
            resp = client.post(
                f"{base_url.rstrip('/')}/rest/auth/angelbroking/user/v1/loginByPassword",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-PrivateKey": api_key,
                    "X-UserType": "USER",
                    "X-SourceID": "WEB",
                    "X-ClientLocalIP": "127.0.0.1",
                    "X-ClientPublicIP": "127.0.0.1",
                    "X-MACAddress": "00:00:00:00:00:00",
                },
                json=payload,
            )
            data = resp.json()
            if resp.status_code >= 400 or data.get("status") is False:
                raise RuntimeError(data.get("message") or data)
            d = data.get("data") or {}
            jwt = str(d.get("jwtToken") or "")
            if not jwt:
                raise RuntimeError("SmartAPI login did not return jwtToken.")
            return AngelOneSession(
                jwt_token=jwt,
                refresh_token=str(d.get("refreshToken") or "") or None,
                feed_token=str(d.get("feedToken") or "") or None,
                client_code=client_code,
            )

    def get_profile(self) -> Dict[str, Any]:
        data = self._request("GET", "/rest/secure/angelbroking/user/v1/getProfile")
        return data.get("data") if isinstance(data, dict) else data

    def list_holdings(self) -> List[Dict[str, Any]]:
        data = self._request("GET", "/rest/secure/angelbroking/portfolio/v1/getHolding")
        items = (data.get("data") if isinstance(data, dict) else None) or []
        return items if isinstance(items, list) else []

    def list_positions(self) -> List[Dict[str, Any]]:
        data = self._request("GET", "/rest/secure/angelbroking/order/v1/getPosition")
        items = (data.get("data") if isinstance(data, dict) else None) or []
        return items if isinstance(items, list) else []

    def list_orders(self) -> List[Dict[str, Any]]:
        data = self._request("GET", "/rest/secure/angelbroking/order/v1/getOrderBook")
        items = (data.get("data") if isinstance(data, dict) else None) or []
        return items if isinstance(items, list) else []

    def get_ltp(self, *, exchange: str, tradingsymbol: str, symboltoken: str) -> float:
        payload = {
            "exchange": exchange,
            "tradingsymbol": tradingsymbol,
            "symboltoken": symboltoken,
        }
        data = self._request(
            "POST",
            "/rest/secure/angelbroking/market/v1/ltpData",
            json_body=payload,
        )
        d = data.get("data") if isinstance(data, dict) else {}
        ltp = d.get("ltp") if isinstance(d, dict) else None
        return float(ltp) if ltp is not None else 0.0

    def place_order(
        self,
        *,
        exchange: str,
        tradingsymbol: str,
        symboltoken: str,
        transactiontype: str,
        quantity: int,
        ordertype: str = "MARKET",
        producttype: str = "CNC",
        price: float | None = None,
        triggerprice: float | None = None,
    ) -> AngelOneOrderResult:
        payload: Dict[str, Any] = {
            "variety": "NORMAL",
            "tradingsymbol": tradingsymbol,
            "symboltoken": symboltoken,
            "transactiontype": transactiontype,
            "exchange": exchange,
            "ordertype": ordertype,
            "producttype": producttype,
            "duration": "DAY",
            "quantity": int(quantity),
        }
        if price is not None:
            payload["price"] = float(price)
        if triggerprice is not None:
            payload["triggerprice"] = float(triggerprice)

        data = self._request(
            "POST",
            "/rest/secure/angelbroking/order/v1/placeOrder",
            json_body=payload,
        )
        d = data.get("data") if isinstance(data, dict) else {}
        order_id = ""
        if isinstance(d, dict):
            order_id = str(d.get("orderid") or d.get("orderId") or "")
        if not order_id:
            order_id = str(data.get("orderid") or data.get("orderId") or "")
        if not order_id:
            raise RuntimeError("SmartAPI order placement did not return order id.")
        raw_obj: Dict[str, Any]
        if isinstance(data, dict):
            raw_obj = data
        else:
            raw_obj = {"raw": data}
        return AngelOneOrderResult(order_id=order_id, raw=raw_obj)


__all__ = ["AngelOneClient", "AngelOneSession", "AngelOneOrderResult"]
