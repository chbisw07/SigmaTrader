from __future__ import annotations

import os

from app.core.auth import hash_password
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import User


def setup_module() -> None:  # type: ignore[override]
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    os.environ["ST_CRYPTO_KEY"] = "test-zerodha-margins-live-balance"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_zerodha_margins_prefers_live_balance(monkeypatch) -> None:
    settings = get_settings()

    import app.api.zerodha as mod

    class _FakeKite:
        def margins(self, segment: str):
            assert segment == "equity"
            return {
                "available": {
                    "cash": 651_976.20,
                    "live_balance": 685_803.56,
                }
            }

    monkeypatch.setattr(mod, "_get_kite_for_user", lambda *_a, **_k: _FakeKite())

    with SessionLocal() as db:
        user = User(
            username="u",
            password_hash=hash_password("pw"),
            role="TRADER",
            display_name="U",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        res = mod.zerodha_margins(db=db, settings=settings, user=user)
        assert isinstance(res, dict)
        assert float(res["available"]) == 685_803.56

