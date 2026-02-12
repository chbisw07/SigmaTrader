from __future__ import annotations

import os
from datetime import date, datetime
from types import SimpleNamespace

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import BrokerConnection, HoldingsSummarySnapshot, User
from app.services import holdings_summary_finalizer as finalizer


def setup_module() -> None:  # type: ignore[override]
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    os.environ["ST_CRYPTO_KEY"] = "test-holdings-summary-finalizer"
    get_settings.cache_clear()

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_finalizer_does_not_overwrite_performance_fields_on_existing_row(monkeypatch) -> None:
    settings = get_settings()

    # Force a deterministic weekday and pre-open time.
    monkeypatch.setattr(finalizer, "_as_of_date_ist", lambda _dt: date(2026, 2, 12))
    monkeypatch.setattr(finalizer, "_now_ist_naive", lambda: datetime(2026, 2, 12, 8, 45, 0))

    called: list[bool] = []

    def fake_capture_snapshot_for_user(*_args, update_performance_fields: bool, **_kwargs):
        called.append(bool(update_performance_fields))
        return SimpleNamespace(id=1)

    monkeypatch.setattr(finalizer, "_capture_snapshot_for_user", fake_capture_snapshot_for_user)
    monkeypatch.setattr(finalizer, "record_system_event", lambda *_args, **_kwargs: None)

    with SessionLocal() as db:
        db.add(User(id=1, username="u1", password_hash="x", role="ADMIN"))
        db.commit()
        db.add(
            BrokerConnection(
                user_id=1,
                broker_name="zerodha",
                access_token_encrypted="x",
            )
        )
        db.add(
            HoldingsSummarySnapshot(
                user_id=1,
                broker_name="zerodha",
                as_of_date=date(2026, 2, 11),
                today_pnl_pct=1.23,
                today_win_rate=45.6,
            )
        )
        db.commit()

    # When overwrite_existing=True, the finalizer should preserve performance fields
    # for an existing snapshot (i.e., pass update_performance_fields=False).
    finalizer._finalize_prev_trading_day(  # noqa: SLF001
        settings=settings,
        mode="window",
        overwrite_existing=True,
    )

    assert called == [False]
