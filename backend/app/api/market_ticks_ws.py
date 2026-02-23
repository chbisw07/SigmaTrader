from __future__ import annotations

import asyncio
import base64
import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, WebSocket
from sqlalchemy.orm import Session

from app.core.auth import SESSION_COOKIE_NAME, decode_session_token
from app.core.config import Settings, get_settings
from app.core.crypto import decrypt_token
from app.db.session import SessionLocal
from app.models import BrokerConnection, User
from app.services.broker_secrets import get_broker_secret

router = APIRouter()


def _now_ist_iso() -> str:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()
    except Exception:
        # Fallback: UTC (still ISO8601).
        return datetime.now(UTC).isoformat()


def _require_ws_admin_user(websocket: WebSocket, *, db: Session, settings: Settings) -> User:
    """Authenticate websocket using the same session cookie as the web UI.

    Mirrors the "any authenticated user is allowed" semantics used by require_admin
    for HTTP APIs. Optionally supports legacy HTTP Basic if configured.
    """

    # Under pytest keep things open.
    if os.getenv("PYTEST_CURRENT_TEST"):
        user = db.query(User).order_by(User.id.asc()).first()
        if user is None:
            raise RuntimeError("No users found under pytest.")
        return user

    token = websocket.cookies.get(SESSION_COOKIE_NAME)
    if token:
        user_id, _payload = decode_session_token(settings, token)
        user = db.query(User).filter(User.id == int(user_id)).one_or_none()
        if user is None:
            raise RuntimeError("User not found for this session.")
        return user

    # Legacy HTTP Basic fallback if configured.
    admin_username = (settings.admin_username or "").strip()
    admin_password = settings.admin_password or ""
    if admin_username and admin_password:
        auth = websocket.headers.get("authorization") or ""
        if auth.lower().startswith("basic "):
            try:
                raw = base64.b64decode(auth.split(" ", 1)[1]).decode("utf-8")
                username, password = raw.split(":", 1)
            except Exception:
                username, password = "", ""
            if username == admin_username and password == admin_password:
                user = db.query(User).filter(User.username == admin_username).one_or_none()
                if user is not None:
                    return user
                raise RuntimeError("Admin user not found.")

    raise RuntimeError("Administrator session required.")


def _build_zerodha_client_for_user(db: Session, settings: Settings, *, user: User):
    try:
        from kiteconnect import KiteConnect  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover - defensive
        raise RuntimeError("kiteconnect library is not installed in the backend environment.") from exc

    conn = (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.broker_name == "zerodha",
            BrokerConnection.user_id == int(user.id),
        )
        .one_or_none()
    )
    if conn is None:
        raise RuntimeError("Zerodha is not connected.")

    api_key = get_broker_secret(
        db,
        settings,
        broker_name="zerodha",
        key="api_key",
        user_id=int(user.id),
    )
    if not api_key:
        raise RuntimeError("Zerodha API key is not configured.")

    access_token = decrypt_token(settings, conn.access_token_encrypted)
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)

    from app.clients.zerodha import ZerodhaClient

    return ZerodhaClient(kite)


def _normalize_subscription(payload: Any) -> list[tuple[str, str]]:
    if not isinstance(payload, dict):
        return []
    if (payload.get("type") or "") != "subscribe":
        return []
    raw = payload.get("symbols")
    if not isinstance(raw, list):
        return []
    out: list[tuple[str, str]] = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        sym = (it.get("symbol") or "").strip().upper()
        exch = (it.get("exchange") or "NSE").strip().upper() or "NSE"
        if not sym:
            continue
        out.append((exch, sym))
    # De-dupe while preserving order.
    seen = set()
    uniq: list[tuple[str, str]] = []
    for k in out:
        if k in seen:
            continue
        seen.add(k)
        uniq.append(k)
    return uniq[:300]


@router.websocket("/ws/market/ticks")
async def market_ticks_ws(websocket: WebSocket) -> None:
    """Best-effort 1s quote stream for holdings live prices.

    Protocol:
      - client sends: {"type":"subscribe","symbols":[{"exchange":"NSE","symbol":"INFY"},...]}
      - server sends: {"type":"ticks","ts":"...","data":[{"exchange":"NSE","symbol":"INFY","ltp":1850.1,"prevClose":1834.0},...]}
    """

    settings = get_settings()
    await websocket.accept()

    with SessionLocal() as db:
        try:
            user = _require_ws_admin_user(websocket, db=db, settings=settings)
            client = _build_zerodha_client_for_user(db, settings, user=user)
        except Exception as exc:
            await websocket.send_json({"type": "error", "error": str(exc)})
            await websocket.close(code=1008)
            return

    lock = asyncio.Lock()
    subscribed: list[tuple[str, str]] = []

    async def _recv_loop() -> None:
        nonlocal subscribed
        while True:
            msg = await websocket.receive_json()
            sub = _normalize_subscription(msg)
            if not sub:
                continue
            async with lock:
                subscribed = sub

    async def _send_loop() -> None:
        while True:
            await asyncio.sleep(1.0)
            async with lock:
                keys = list(subscribed)
            if not keys:
                continue
            # Quote API expects broker tradingsymbols; map app symbols when configured.
            try:
                from app.services.market_data import _map_app_symbol_to_zerodha_symbol

                mapped: list[tuple[str, str]] = []
                back: dict[tuple[str, str], tuple[str, str]] = {}
                for exch, sym in keys:
                    broker_sym = _map_app_symbol_to_zerodha_symbol(exch, sym)
                    mapped_key = (exch, broker_sym)
                    mapped.append(mapped_key)
                    back[mapped_key] = (exch, sym)

                quotes = client.get_quote_bulk(mapped)
                rows: list[dict[str, Any]] = []
                for mapped_key, q in quotes.items():
                    orig = back.get(mapped_key)
                    if orig is None:
                        continue
                    ltp = q.get("last_price")
                    if ltp is None:
                        continue
                    try:
                        ltp_f = float(ltp)
                    except Exception:
                        continue
                    prev = q.get("prev_close")
                    prev_f: float | None
                    try:
                        prev_f = float(prev) if prev is not None else None
                    except Exception:
                        prev_f = None
                    rows.append(
                        {
                            "exchange": orig[0],
                            "symbol": orig[1],
                            "ltp": ltp_f,
                            "prevClose": prev_f,
                        }
                    )
            except Exception:
                # Avoid killing the socket on transient broker errors.
                continue

            if rows:
                await websocket.send_json(
                    {
                        "type": "ticks",
                        "ts": _now_ist_iso(),
                        "data": rows,
                    }
                )

    recv_task = asyncio.create_task(_recv_loop())
    send_task = asyncio.create_task(_send_loop())
    done, pending = await asyncio.wait(
        {recv_task, send_task},
        return_when=asyncio.FIRST_EXCEPTION,
    )
    for task in pending:
        task.cancel()
    for task in done:
        _ = task.exception()
