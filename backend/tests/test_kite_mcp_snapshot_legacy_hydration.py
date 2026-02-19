from __future__ import annotations

import os
from datetime import UTC, datetime

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import EquitySnapshot, HoldingsSummarySnapshot, Position, PositionSnapshot, User
from app.schemas.ai_trading_manager import BrokerPosition, BrokerSnapshot
from app.services.kite_mcp.legacy_cache import hydrate_legacy_caches_from_kite_mcp_snapshot


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_CRYPTO_KEY"] = "test-kite-mcp-legacy-hydration"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_hydrate_legacy_caches_writes_positions_and_snapshots() -> None:
    now = datetime(2026, 2, 19, 12, 0, 0, tzinfo=UTC)
    snap = BrokerSnapshot(
        as_of_ts=now,
        account_id="default",
        source="kite_mcp",
        holdings=[
            {
                "tradingsymbol": "ABC",
                "quantity": 10,
                "average_price": 100,
                "last_price": 110,
            }
        ],
        positions=[
            BrokerPosition(symbol="ABC", product="CNC", qty=10, avg_price=100.0),
        ],
        orders=[],
        margins={"equity": {"net": 12345.0, "available": {"cash": 2500.0}}},
        quotes_cache=[],
    )

    with SessionLocal() as db:
        user = User(
            username="admin",
            password_hash="dummy",
            role="ADMIN",
            display_name="Admin",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        out = hydrate_legacy_caches_from_kite_mcp_snapshot(db, snapshot=snap, user=user)
        assert out["positions_written"] == 1
        assert out["position_snapshots_written"] == 1
        assert out["holdings_summary_written"] == 1
        assert out["equity_snapshot_written"] == 1

        assert db.query(Position).count() == 1
        assert db.query(PositionSnapshot).count() == 1
        assert db.query(HoldingsSummarySnapshot).count() == 1
        assert db.query(EquitySnapshot).count() == 1

