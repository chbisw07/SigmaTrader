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
from app.services.broker_secrets import get_broker_secret

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


class AngelOneConnectRequest(BaseModel):
    client_code: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    totp: str = Field(..., min_length=1)


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


__all__ = ["router"]
