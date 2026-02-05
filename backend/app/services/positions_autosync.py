from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from threading import Lock, Thread
from typing import Any

from sqlalchemy.orm import Session

from app.clients import ZerodhaClient
from app.core.config import Settings
from app.core.crypto import decrypt_token
from app.db.session import SessionLocal
from app.models import BrokerConnection
from app.services.broker_secrets import get_broker_secret
from app.services.positions_sync import sync_positions_from_zerodha
from app.services.system_events import record_system_event

_state_lock = Lock()
_state: dict[tuple[str, int], dict[str, Any]] = {}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _should_schedule(*, key: tuple[str, int], min_interval: timedelta) -> bool:
    st = _state.get(key) or {}
    if st.get("pending"):
        return False
    last_done: datetime | None = st.get("last_done_at")
    if last_done is not None and (_utc_now() - last_done) < min_interval:
        return False
    return True


def _build_zerodha_client(db: Session, settings: Settings, *, user_id: int) -> ZerodhaClient:
    conn = (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.broker_name == "zerodha",
            BrokerConnection.user_id == user_id,
        )
        .order_by(BrokerConnection.updated_at.desc())
        .first()
    )
    if conn is None:
        raise RuntimeError("Zerodha is not connected.")

    api_key = get_broker_secret(
        db,
        settings,
        broker_name="zerodha",
        key="api_key",
        user_id=user_id,
    )
    if not api_key:
        raise RuntimeError("Zerodha API key is not configured.")

    try:
        from kiteconnect import KiteConnect  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover - defensive
        raise RuntimeError(
            "kiteconnect library is not installed in the backend environment."
        ) from exc

    access_token = decrypt_token(settings, conn.access_token_encrypted)
    kite = KiteConnect(api_key=str(api_key).strip())
    kite.set_access_token(access_token)
    return ZerodhaClient(kite)


def schedule_positions_autosync(
    *,
    settings: Settings,
    broker_name: str,
    user_id: int,
    reason: str,
    delay_seconds: float = 2.0,
    min_interval_seconds: float = 15.0,
) -> bool:
    """Schedule a best-effort broker sync to refresh cached positions.

    This is a fallback for cases where broker webhooks/postbacks are not
    configured or not delivered. It is intentionally throttled and does not
    block order execution responses.
    """

    broker = (broker_name or "").strip().lower()
    if broker != "zerodha":
        return False

    key = (broker, int(user_id))
    min_interval = timedelta(seconds=float(min_interval_seconds))

    with _state_lock:
        if not _should_schedule(key=key, min_interval=min_interval):
            return False
        _state[key] = {
            **(_state.get(key) or {}),
            "pending": True,
            "pending_since": _utc_now(),
        }

    def _run() -> None:  # pragma: no cover - background thread
        updated: int | None = None
        error: str | None = None
        db: Session | None = None
        try:
            if delay_seconds and delay_seconds > 0:
                time.sleep(float(delay_seconds))
            db = SessionLocal()
            client = _build_zerodha_client(db, settings, user_id=int(user_id))
            updated = int(sync_positions_from_zerodha(db, client))
        except Exception as exc:
            error = str(exc)
        finally:
            try:
                if db is not None:
                    if error:
                        try:
                            record_system_event(
                                db,
                                level="ERROR",
                                category="positions_autosync",
                                message="Positions autosync failed",
                                details={
                                    "broker": broker,
                                    "user_id": int(user_id),
                                    "reason": reason,
                                    "error": error,
                                },
                            )
                        except Exception:
                            pass
                    else:
                        try:
                            record_system_event(
                                db,
                                level="INFO",
                                category="positions_autosync",
                                message="Positions autosync complete",
                                details={
                                    "broker": broker,
                                    "user_id": int(user_id),
                                    "reason": reason,
                                    "updated": updated,
                                },
                            )
                        except Exception:
                            pass
            finally:
                try:
                    if db is not None:
                        db.close()
                finally:
                    with _state_lock:
                        _state[key] = {
                            **(_state.get(key) or {}),
                            "pending": False,
                            "last_done_at": _utc_now(),
                        }

    Thread(
        target=_run,
        name=f"positions-autosync-{broker}-{int(user_id)}",
        daemon=True,
    ).start()
    return True


def _reset_autosync_state_for_tests() -> None:
    with _state_lock:
        _state.clear()


__all__ = ["schedule_positions_autosync"]
