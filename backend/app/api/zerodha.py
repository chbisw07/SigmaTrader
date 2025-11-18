from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.clients import ZerodhaClient
from app.core.config import Settings, get_settings
from app.core.crypto import decrypt_token, encrypt_token
from app.db.session import get_db
from app.models import BrokerConnection, User
from app.services.broker_secrets import get_broker_secret
from app.services.order_sync import sync_order_statuses
from app.services.system_events import record_system_event

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


class ZerodhaConnectRequest(BaseModel):
    request_token: str


class SyncOrdersResponse(BaseModel):
    updated: int


class MarginsResponse(BaseModel):
    available: float
    raw: Dict[str, Any]


class OrderPreviewRequest(BaseModel):
    symbol: str
    exchange: str = "NSE"
    side: str
    qty: float
    product: str
    order_type: str
    price: float | None = None
    trigger_price: float | None = None


class OrderPreviewResponse(BaseModel):
    required: float
    charges: Dict[str, Any] | None = None
    currency: str | None = None
    raw: Dict[str, Any]


@router.get("/login-url")
def get_login_url(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> Dict[str, str]:
    """Return the Zerodha login URL for manual OAuth flow."""

    api_key = get_broker_secret(
        db,
        settings,
        broker_name="zerodha",
        key="api_key",
        user_id=user.id,
    )
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zerodha API key is not configured. "
            "Please configure it in the broker settings.",
        )

    url = f"https://kite.zerodha.com/connect/login?v=3&api_key={api_key}"
    return {"login_url": url}


@router.post("/connect")
def connect_zerodha(
    payload: ZerodhaConnectRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> Dict[str, str]:
    """Exchange a request_token for access_token and store it encrypted."""

    api_key = get_broker_secret(
        db,
        settings,
        broker_name="zerodha",
        key="api_key",
        user_id=user.id,
    )
    api_secret = get_broker_secret(
        db,
        settings,
        broker_name="zerodha",
        key="api_secret",
        user_id=user.id,
    )
    if not api_key or not api_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Zerodha API key/secret are not configured. "
                "Please configure them in the broker settings."
            ),
        )

    try:
        from kiteconnect import KiteConnect  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="kiteconnect library is not installed in the backend environment.",
        ) from exc

    kite = KiteConnect(api_key=api_key)
    session_data = kite.generate_session(
        payload.request_token,
        api_secret=api_secret,
    )
    access_token = session_data.get("access_token")
    if not access_token:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Zerodha did not return an access_token.",
        )

    encrypted = encrypt_token(settings, access_token)

    # Fetch broker profile so we can persist the broker-side user/account id.
    kite.set_access_token(access_token)
    try:
        profile = kite.profile()
        broker_user_id = profile.get("user_id")
    except Exception:  # pragma: no cover - defensive
        broker_user_id = None

    conn = (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.broker_name == "zerodha",
            BrokerConnection.user_id == user.id,
        )
        .one_or_none()
    )
    if conn is None:
        conn = BrokerConnection(
            user_id=user.id,
            broker_name="zerodha",
            access_token_encrypted=encrypted,
            broker_user_id=broker_user_id,
        )
        db.add(conn)
    else:
        conn.access_token_encrypted = encrypted
        conn.broker_user_id = broker_user_id or conn.broker_user_id

    db.commit()

    # Log a minimal audit entry with correlation id.
    correlation_id = getattr(request.state, "correlation_id", None)
    import logging

    logging.getLogger(__name__).info(
        "Zerodha connection updated",
        extra={
            "extra": {
                "correlation_id": correlation_id,
                "broker": "zerodha",
            }
        },
    )

    record_system_event(
        db,
        level="INFO",
        category="broker",
        message="Zerodha connection updated",
        correlation_id=correlation_id,
        details={"broker": "zerodha"},
    )

    return {"status": "connected"}


def _get_kite_for_user(
    db: Session,
    settings: Settings,
    user: User,
):
    """Construct a KiteConnect client for the given user."""

    conn = (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.broker_name == "zerodha",
            BrokerConnection.user_id == user.id,
        )
        .one_or_none()
    )
    if conn is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zerodha is not connected.",
        )

    api_key = get_broker_secret(
        db,
        settings,
        broker_name="zerodha",
        key="api_key",
        user_id=user.id,
    )
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zerodha API key is not configured. "
            "Please configure it in the broker settings.",
        )

    try:
        from kiteconnect import KiteConnect  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="kiteconnect library is not installed in the backend environment.",
        ) from exc

    access_token = decrypt_token(settings, conn.access_token_encrypted)
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite


@router.get("/status")
def zerodha_status(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return whether Zerodha is connected and optionally basic profile info."""

    conn = (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.broker_name == "zerodha",
            BrokerConnection.user_id == user.id,
        )
        .one_or_none()
    )
    if conn is None:
        return {"connected": False}

    updated_at = conn.updated_at.isoformat() if conn.updated_at else None

    try:
        kite = _get_kite_for_user(db, settings, user)
        profile = kite.profile()

        # Persist broker-side user id on the connection so that other
        # parts of the system (e.g. order execution) can stamp it onto
        # orders without needing to call profile() again.
        broker_user_id = profile.get("user_id")
        if broker_user_id and getattr(conn, "broker_user_id", None) != broker_user_id:
            conn.broker_user_id = broker_user_id  # type: ignore[attr-defined]
            db.add(conn)
            db.commit()

        return {
            "connected": True,
            "updated_at": updated_at,
            "user_id": profile.get("user_id"),
            "user_name": profile.get("user_name"),
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "connected": False,
            "updated_at": updated_at,
            "error": str(exc),
        }


@router.post("/sync-orders", response_model=SyncOrdersResponse)
def sync_orders(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> Dict[str, int]:
    """Synchronize local Order rows with Zerodha order statuses."""

    conn = (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.broker_name == "zerodha",
            BrokerConnection.user_id == user.id,
        )
        .one_or_none()
    )
    if conn is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zerodha is not connected.",
        )

    kite = _get_kite_for_user(db, settings, user)

    client = ZerodhaClient(kite)
    updated = sync_order_statuses(db, client)
    return {"updated": updated}


@router.get("/margins", response_model=MarginsResponse)
def zerodha_margins(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return basic margin/funds information for the current Zerodha user."""

    kite = _get_kite_for_user(db, settings, user)
    data = kite.margins("equity")
    # When segment is provided, KiteConnect may either return the segment
    # object directly or nested under the segment key. Handle both.
    segment: Dict[str, Any]
    if isinstance(data, dict) and "equity" in data:
        segment = data["equity"]
    else:
        segment = data

    available_section = segment.get("available") or {}
    # Prefer cash margin; fall back to any numeric value we can find.
    available_raw = (
        available_section.get("cash")
        or available_section.get("live_balance")
        or available_section.get("opening_balance")
        or 0.0
    )
    try:
        available = float(available_raw)
    except (TypeError, ValueError):
        available = 0.0

    return MarginsResponse(available=available, raw=segment).dict()


@router.post("/order-preview", response_model=OrderPreviewResponse)
def zerodha_order_preview(
    payload: OrderPreviewRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return a margin/charges preview for a hypothetical Zerodha order."""

    kite = _get_kite_for_user(db, settings, user)

    symbol = payload.symbol
    exchange = payload.exchange or "NSE"
    if ":" in symbol:
        ex, ts = symbol.split(":", 1)
        if ex:
            exchange = ex
        tradingsymbol = ts
    else:
        tradingsymbol = symbol

    order: Dict[str, Any] = {
        "exchange": exchange,
        "tradingsymbol": tradingsymbol,
        "transaction_type": payload.side.upper(),
        "quantity": int(payload.qty),
        "product": payload.product.upper(),
        "order_type": payload.order_type.upper(),
        "variety": "regular",
    }
    if payload.price is not None:
        order["price"] = float(payload.price)
    if payload.trigger_price is not None:
        order["trigger_price"] = float(payload.trigger_price)

    preview_list = kite.order_margins([order])
    if not preview_list:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Zerodha did not return margin details for the preview request.",
        )

    entry = preview_list[0]
    required_raw = entry.get("total") or entry.get("margin") or 0.0
    try:
        required = float(required_raw)
    except (TypeError, ValueError):
        required = 0.0

    charges = entry.get("charges") or None
    currency = entry.get("currency") or entry.get("settlement_currency")

    return OrderPreviewResponse(
        required=required,
        charges=charges,
        currency=currency,
        raw=entry,
    ).dict()


__all__ = ["router"]
