from __future__ import annotations

import os
from typing import Any, Dict

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import BrokerConnection

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_TRADINGVIEW_WEBHOOK_SECRET"] = "positions-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Seed a fake broker connection so the sync endpoint can proceed
    # without actually talking to Zerodha in this test.
    with SessionLocal() as session:
        conn = BrokerConnection(
            broker_name="zerodha",
            access_token_encrypted="dummy-token",
        )
        session.add(conn)
        session.commit()


class _FakeClient:
    def __init__(self) -> None:
        self._positions: Dict[str, Any] = {
            "net": [
                {
                    "tradingsymbol": "INFY",
                    "product": "CNC",
                    "quantity": 10,
                    "average_price": 1500.0,
                    "pnl": 120.0,
                }
            ]
        }

    def list_positions(self) -> Dict[str, Any]:
        return self._positions


def test_sync_positions_populates_db(monkeypatch: Any) -> None:
    from app.api import positions as positions_api
    from app.services import positions_sync

    # Monkeypatch Zerodha client builder and use a fake client for sync.
    fake_client = _FakeClient()

    def _fake_get_client(db: Any, settings: Any) -> _FakeClient:
        return fake_client

    monkeypatch.setattr(
        positions_api, "_get_zerodha_client_for_positions", _fake_get_client
    )

    def _fake_sync(db: Any, client: Any) -> int:
        return positions_sync.sync_positions_from_zerodha(db, client)  # type: ignore[arg-type]

    monkeypatch.setattr(positions_api, "sync_positions_from_zerodha", _fake_sync)

    resp = client.post("/api/positions/sync")
    assert resp.status_code == 200
    data = resp.json()
    assert data["updated"] == 1

    resp_list = client.get("/api/positions/")
    assert resp_list.status_code == 200
    positions_payload = resp_list.json()
    assert len(positions_payload) == 1
    p = positions_payload[0]
    assert p["symbol"] == "INFY"
    assert p["product"] == "CNC"
    assert p["qty"] == 10
    assert p["avg_price"] == 1500.0
