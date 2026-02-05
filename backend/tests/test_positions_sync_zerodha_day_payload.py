from __future__ import annotations

import os
from typing import Any, Dict

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import Position, PositionSnapshot
from app.services.positions_sync import sync_positions_from_zerodha


def setup_module() -> None:  # type: ignore[override]
    os.environ.setdefault("ST_CRYPTO_KEY", "test-positions-sync-crypto-key")
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


class _FakeClient:
    def __init__(self) -> None:
        # Typical Zerodha shape: `day` contains intraday activity even when net=0.
        self._positions: Dict[str, Any] = {
            "net": [],
            "day": [
                {
                    "tradingsymbol": "INFY",
                    "exchange": "NSE",
                    "product": "MIS",
                    "quantity": 0,
                    "average_price": 1500.0,
                    "pnl": 0.0,
                    "day_buy_quantity": 10,
                    "day_buy_price": 1500.0,
                    "day_sell_quantity": 10,
                    "day_sell_price": 1510.0,
                }
            ],
        }

    def list_positions(self) -> Dict[str, Any]:
        return self._positions


def test_sync_positions_uses_day_rows_for_snapshots_when_net_empty() -> None:
    fake = _FakeClient()
    with SessionLocal() as session:
        updated = sync_positions_from_zerodha(session, fake)  # type: ignore[arg-type]
        assert updated == 1

        # Open positions cache should be empty (net was empty).
        assert session.query(Position).count() == 0

        snaps = session.query(PositionSnapshot).all()
        assert len(snaps) == 1
        assert snaps[0].symbol == "INFY"
        assert snaps[0].qty == 0

