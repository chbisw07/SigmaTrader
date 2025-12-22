from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.clients import AngelOneClient, AngelOneSession
from app.core.config import Settings, get_settings
from app.core.crypto import decrypt_token, encrypt_token
from app.db.session import get_db
from app.models import BrokerConnection, User
from app.services.broker_instruments import resolve_broker_symbol_and_token
from app.services.broker_secrets import get_broker_secret

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


class AngelOneConnectRequest(BaseModel):
    client_code: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    totp: str = Field(..., min_length=1)


class LtpResponse(BaseModel):
    ltp: float


def _get_angelone_client(
    db: Session,
    settings: Settings,
    *,
    user: User,
) -> AngelOneClient:
    conn = (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.broker_name == "angelone",
            BrokerConnection.user_id == user.id,
        )
        .one_or_none()
    )
    if conn is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AngelOne is not connected.",
        )

    api_key = get_broker_secret(
        db,
        settings,
        broker_name="angelone",
        key="api_key",
        user_id=user.id,
    )
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "SmartAPI API key is not configured. "
                "Please add api_key in broker settings."
            ),
        )

    raw = decrypt_token(settings, conn.access_token_encrypted)
    try:
        parsed = json.loads(raw) if raw else {}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"AngelOne session is invalid: {exc}",
        ) from exc

    jwt = str(parsed.get("jwt_token") or "")
    if not jwt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AngelOne session is missing jwt_token. Please reconnect.",
        )

    session = AngelOneSession(
        jwt_token=jwt,
        refresh_token=str(parsed.get("refresh_token") or "") or None,
        feed_token=str(parsed.get("feed_token") or "") or None,
        client_code=str(parsed.get("client_code") or "") or None,
    )
    return AngelOneClient(api_key=api_key, session=session)


@router.post("/connect")
def connect_angelone(
    payload: AngelOneConnectRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    api_key = get_broker_secret(
        db,
        settings,
        broker_name="angelone",
        key="api_key",
        user_id=user.id,
    )
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "SmartAPI API key is not configured. "
                "Please add api_key in broker settings."
            ),
        )

    try:
        session = AngelOneClient.login(
            api_key=api_key,
            client_code=payload.client_code.strip(),
            password=payload.password.strip(),
            totp=payload.totp.strip(),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"AngelOne connect failed: {exc}",
        ) from exc

    session_blob = {
        "jwt_token": session.jwt_token,
        "refresh_token": session.refresh_token,
        "feed_token": session.feed_token,
        "client_code": session.client_code,
    }
    encrypted = encrypt_token(settings, json.dumps(session_blob, default=str))

    conn = (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.broker_name == "angelone",
            BrokerConnection.user_id == user.id,
        )
        .one_or_none()
    )
    if conn is None:
        conn = BrokerConnection(
            user_id=user.id,
            broker_name="angelone",
            access_token_encrypted=encrypted,
        )
        db.add(conn)
    else:
        conn.access_token_encrypted = encrypted

    db.commit()
    db.refresh(conn)

    # Best-effort: fetch profile and persist broker_user_id.
    try:
        client = AngelOneClient(api_key=api_key, session=session)
        profile = client.get_profile()
        broker_user_id = profile.get("clientcode") or profile.get("clientCode")
        if broker_user_id and conn.broker_user_id != str(broker_user_id):
            conn.broker_user_id = str(broker_user_id)
            db.add(conn)
            db.commit()
        return {
            "connected": True,
            "updated_at": conn.updated_at.isoformat(),
            "client_code": payload.client_code.strip(),
        }
    except Exception:
        return {
            "connected": True,
            "updated_at": conn.updated_at.isoformat(),
            "client_code": payload.client_code.strip(),
        }


@router.get("/status")
def angelone_status(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    conn = (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.broker_name == "angelone",
            BrokerConnection.user_id == user.id,
        )
        .one_or_none()
    )
    if conn is None:
        return {"connected": False}

    updated_at = conn.updated_at.isoformat() if conn.updated_at else None
    api_key = get_broker_secret(
        db,
        settings,
        broker_name="angelone",
        key="api_key",
        user_id=user.id,
    )
    if not api_key:
        return {
            "connected": False,
            "updated_at": updated_at,
            "error": "Missing api_key.",
        }

    try:
        raw = decrypt_token(settings, conn.access_token_encrypted)
        parsed = json.loads(raw) if raw else {}
        jwt = str(parsed.get("jwt_token") or "")
        if not jwt:
            return {"connected": False, "updated_at": updated_at}
        session = AngelOneSession(
            jwt_token=jwt,
            refresh_token=str(parsed.get("refresh_token") or "") or None,
            feed_token=str(parsed.get("feed_token") or "") or None,
            client_code=str(parsed.get("client_code") or "") or None,
        )
        client = AngelOneClient(api_key=api_key, session=session)
        profile = client.get_profile()
        return {
            "connected": True,
            "updated_at": updated_at,
            "client_code": profile.get("clientcode") or profile.get("clientCode"),
            "name": profile.get("name") or profile.get("clientname"),
        }
    except Exception as exc:
        return {"connected": False, "updated_at": updated_at, "error": str(exc)}


@router.get("/ltp", response_model=LtpResponse)
def angelone_ltp(
    symbol: str,
    exchange: str = "NSE",
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> LtpResponse:
    exch_u = (exchange or "NSE").strip().upper()
    sym_u = (symbol or "").strip().upper()
    if not sym_u:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="symbol is required.",
        )

    resolved = resolve_broker_symbol_and_token(
        db,
        broker_name="angelone",
        exchange=exch_u,
        symbol=sym_u,
    )
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"AngelOne instrument mapping not found for {exch_u}:{sym_u}. "
                "Please run Instruments → Sync for AngelOne."
            ),
        )
    broker_symbol, token = resolved
    client = _get_angelone_client(db, settings, user=user)
    try:
        ltp = float(
            client.get_ltp(
                exchange=exch_u,
                tradingsymbol=broker_symbol,
                symboltoken=token,
            )
        )
    except Exception as exc:  # pragma: no cover - broker/network
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AngelOne LTP fetch failed: {exc}",
        ) from exc
    return LtpResponse(ltp=ltp)


__all__ = ["router"]
