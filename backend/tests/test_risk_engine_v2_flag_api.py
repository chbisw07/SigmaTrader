from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.main import app

client = TestClient(app)

def setup_module() -> None:  # type: ignore[override]
    os.environ.setdefault("ST_CRYPTO_KEY", "test-risk-engine-v2-flag-crypto-key")
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

def teardown_module() -> None:  # type: ignore[override]
    get_settings.cache_clear()


def test_v2_flag_defaults_to_unified_global_when_db_missing() -> None:
    res = client.get("/api/risk-engine/v2-enabled")
    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is False
    assert data["source"] == "env_default"


def test_v2_flag_put_persists_to_unified_global() -> None:
    put = client.put("/api/risk-engine/v2-enabled", json={"enabled": False})
    assert put.status_code == 200
    put_data = put.json()
    assert put_data["enabled"] is False
    assert put_data["source"] == "db"

    get = client.get("/api/risk-engine/v2-enabled")
    assert get.status_code == 200
    get_data = get.json()
    assert get_data["enabled"] is False
    assert get_data["source"] == "db"
