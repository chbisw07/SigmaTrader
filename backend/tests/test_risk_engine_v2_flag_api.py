from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.main import app

client = TestClient(app)

_ORIG_V2_ENV = os.environ.get("ST_RISK_ENGINE_V2_ENABLED")

def setup_module() -> None:  # type: ignore[override]
    os.environ.setdefault("ST_CRYPTO_KEY", "test-risk-engine-v2-flag-crypto-key")
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

def teardown_module() -> None:  # type: ignore[override]
    if _ORIG_V2_ENV is None:
        os.environ.pop("ST_RISK_ENGINE_V2_ENABLED", None)
    else:
        os.environ["ST_RISK_ENGINE_V2_ENABLED"] = _ORIG_V2_ENV
    get_settings.cache_clear()


def test_v2_flag_defaults_to_env_when_db_missing() -> None:
    os.environ["ST_RISK_ENGINE_V2_ENABLED"] = "0"
    get_settings.cache_clear()
    res = client.get("/api/risk-engine/v2-enabled")
    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is False
    assert data["source"] == "env_default"


def test_v2_flag_put_persists_and_overrides_env() -> None:
    # Turn env ON, but keep the DB override OFF.
    os.environ["ST_RISK_ENGINE_V2_ENABLED"] = "1"
    get_settings.cache_clear()

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

    # Compiled policy should reflect the same DB-driven flag.
    compiled = client.get("/api/risk/compiled?product=CNC&category=LC")
    assert compiled.status_code == 200
    compiled_data = compiled.json()
    assert compiled_data["inputs"]["risk_engine_v2_enabled"] is False
