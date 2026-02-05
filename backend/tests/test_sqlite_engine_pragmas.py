from __future__ import annotations

import os

import pytest

from app.core.config import get_settings
from app.db.session import engine


def setup_module() -> None:  # type: ignore[override]
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    os.environ["ST_CRYPTO_KEY"] = "test-sqlite-engine-pragmas"
    get_settings.cache_clear()


def test_sqlite_engine_pragmas() -> None:
    settings = get_settings()
    if not settings.database_url.startswith("sqlite"):
        pytest.skip("SQLite-specific pragmas only apply for sqlite databases.")

    con = engine.raw_connection()
    try:
        cur = con.cursor()
        cur.execute("PRAGMA journal_mode;")
        mode = cur.fetchone()[0]
        cur.execute("PRAGMA foreign_keys;")
        fk = cur.fetchone()[0]
        cur.close()
    finally:
        con.close()

    assert str(mode).lower() == "wal"
    assert int(fk) == 1

