from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.clients import ZerodhaClient
from app.config_files import load_kite_config
from app.core.config import Settings, get_settings
from app.core.crypto import decrypt_token, encrypt_token
from app.db.session import get_db
from app.models import BrokerConnection
from app.services.order_sync import sync_order_statuses

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


class ZerodhaConnectRequest(BaseModel):
    request_token: str


class SyncOrdersResponse(BaseModel):
    updated: int


@router.get("/login-url")
def get_login_url() -> Dict[str, str]:
    """Return the Zerodha login URL for manual OAuth flow."""

    kite_cfg = load_kite_config()
    api_key = kite_cfg.kite_connect.api_key
    url = f"https://kite.zerodha.com/connect/login?v=3&api_key={api_key}"
    return {"login_url": url}


@router.post("/connect")
def connect_zerodha(
    payload: ZerodhaConnectRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Dict[str, str]:
    """Exchange a request_token for access_token and store it encrypted."""

    kite_cfg = load_kite_config()

    try:
        from kiteconnect import KiteConnect  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="kiteconnect library is not installed in the backend environment.",
        ) from exc

    kite = KiteConnect(api_key=kite_cfg.kite_connect.api_key)
    session_data = kite.generate_session(
        payload.request_token,
        api_secret=kite_cfg.kite_connect.api_secret,
    )
    access_token = session_data.get("access_token")
    if not access_token:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Zerodha did not return an access_token.",
        )

    encrypted = encrypt_token(settings, access_token)

    conn = (
        db.query(BrokerConnection)
        .filter(BrokerConnection.broker_name == "zerodha")
        .one_or_none()
    )
    if conn is None:
        conn = BrokerConnection(
            broker_name="zerodha",
            access_token_encrypted=encrypted,
        )
        db.add(conn)
    else:
        conn.access_token_encrypted = encrypted

    db.commit()

    return {"status": "connected"}


@router.get("/status")
def zerodha_status(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """Return whether Zerodha is connected and optionally basic profile info."""

    conn = (
        db.query(BrokerConnection)
        .filter(BrokerConnection.broker_name == "zerodha")
        .one_or_none()
    )
    if conn is None:
        return {"connected": False}

    updated_at = conn.updated_at.isoformat() if conn.updated_at else None

    try:
        kite_cfg = load_kite_config()
        from kiteconnect import KiteConnect  # type: ignore[import]

        access_token = decrypt_token(settings, conn.access_token_encrypted)
        kite = KiteConnect(api_key=kite_cfg.kite_connect.api_key)
        kite.set_access_token(access_token)
        profile = kite.profile()
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
) -> Dict[str, int]:
    """Synchronize local Order rows with Zerodha order statuses."""

    conn = (
        db.query(BrokerConnection)
        .filter(BrokerConnection.broker_name == "zerodha")
        .one_or_none()
    )
    if conn is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zerodha is not connected.",
        )

    kite_cfg = load_kite_config()

    try:
        from kiteconnect import KiteConnect  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="kiteconnect library is not installed in the backend environment.",
        ) from exc

    access_token = decrypt_token(settings, conn.access_token_encrypted)
    kite = KiteConnect(api_key=kite_cfg.kite_connect.api_key)
    kite.set_access_token(access_token)

    client = ZerodhaClient(kite)
    updated = sync_order_statuses(db, client)
    return {"updated": updated}


__all__ = ["router"]
