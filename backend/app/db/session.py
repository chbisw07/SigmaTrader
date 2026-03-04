from __future__ import annotations

import logging
import os
import sys
import threading
from typing import Iterator

from sqlalchemy import event
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy import inspect
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

from .base import Base

settings = get_settings()
logger = logging.getLogger(__name__)

_SCHEMA_ENSURED = False
_SCHEMA_LOCK = threading.Lock()

connect_args: dict[str, object] = {}
if settings.database_url.startswith("sqlite"):
    # Required for SQLite when using the same connection in multiple threads.
    connect_args["check_same_thread"] = False
    # Avoid spurious "database is locked" errors under concurrent reads/writes
    # (background market-data sync + dashboard requests). This makes SQLite wait
    # briefly for locks instead of failing immediately.
    connect_args["timeout"] = 30


engine = create_engine(
    settings.database_url,
    echo=settings.database_echo,
    future=True,
    connect_args=connect_args,
)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # pragma: no cover
    if not settings.database_url.startswith("sqlite"):
        return
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()
    except Exception:
        # Best-effort; app can run without these pragmas.
        return


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def _ensure_sqlite_schema_if_missing() -> None:
    """Bootstrap missing tables for SQLite deployments.

    If the app starts without running migrations (or lifespan hooks are
    disabled), core endpoints can crash with `no such table: users`. For SQLite
    we can safely create missing tables using SQLAlchemy metadata.
    """

    global _SCHEMA_ENSURED
    if _SCHEMA_ENSURED:
        return
    if "pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST"):
        return
    if not settings.database_url.startswith("sqlite"):
        return

    with _SCHEMA_LOCK:
        if _SCHEMA_ENSURED:
            return
        try:
            inspector = inspect(engine)
            tables = set(inspector.get_table_names())
            # Minimal set required for login + broker integrations. If any of
            # these are missing, create_all(checkfirst=True) is a safe,
            # non-destructive way to bootstrap tables for SQLite dev DBs.
            core = {"users", "broker_secrets"}
            missing = sorted(core - tables)
            if not missing:
                _SCHEMA_ENSURED = True
                return

            # Ensure all model modules are imported so Base.metadata is complete.
            from app import models  # noqa: F401

            logger.warning(
                "SQLite schema missing core tables; creating tables with create_all(checkfirst=True).",
                extra={"extra": {"missing_tables": missing}},
            )
            Base.metadata.create_all(bind=engine, checkfirst=True)
        except Exception:
            logger.exception("Failed to ensure SQLite schema.")
        finally:
            _SCHEMA_ENSURED = True


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a database session."""

    _ensure_sqlite_schema_if_missing()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


__all__ = ["engine", "SessionLocal", "get_db", "Base"]

# Ensure background tasks that use SessionLocal() directly (not the FastAPI
# dependency) still see a usable schema in local SQLite deployments.
_ensure_sqlite_schema_if_missing()
