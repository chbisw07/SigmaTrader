import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError

from .api.routes import router as api_router
from .core.config import get_settings
from .core.logging import RequestContextMiddleware, configure_logging
from .db.session import SessionLocal
from .services.alerts_v3 import schedule_alerts_v3
from .services.deployment_runtime import start_deployments_runtime
from .services.instruments_sync import schedule_instrument_master_sync
from .services.market_data import schedule_market_data_sync
from .services.synthetic_gtt import schedule_synthetic_gtt
from .services.users import ensure_default_admin

settings = get_settings()

configure_logging()
logger = logging.getLogger(__name__)


def _run_migrations_if_needed() -> None:
    """Best-effort Alembic migration runner for local/dev usage.

    This prevents runtime errors when the application code expects new columns
    but the developer database file hasn't been upgraded yet.
    """

    if "pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST"):
        return

    auto = (os.getenv("ST_AUTO_MIGRATE") or "").strip().lower()
    if auto in {"0", "false", "no", "off"}:
        return

    should_run = auto in {"1", "true", "yes", "on"} or settings.database_url.startswith(
        "sqlite"
    )
    if not should_run:
        return

    try:
        from alembic import command
        from alembic.config import Config

        backend_root = Path(__file__).resolve().parents[1]
        alembic_ini = backend_root / "alembic.ini"
        if not alembic_ini.exists():
            return

        cfg = Config(str(alembic_ini))
        # Make migration execution independent of the process working directory.
        cfg.set_main_option("script_location", str(backend_root / "alembic"))
        cfg.set_main_option("sqlalchemy.url", settings.database_url)
        command.upgrade(cfg, "head")
    except Exception:
        logger.exception("Failed to run Alembic migrations on startup.")


def _bootstrap_admin_user() -> None:
    """Ensure the default admin user exists at startup."""

    with SessionLocal() as db:
        try:
            inspector = inspect(db.get_bind())
            if "users" not in inspector.get_table_names():
                # Database has not been migrated/created yet; skip bootstrapping.
                return
            ensure_default_admin(db, settings=settings)
        except OperationalError:
            # If the users table is not yet available (e.g., during early test
            # setup or before migrations), silently skip bootstrapping.
            return


_bootstrap_admin_user()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """FastAPI lifespan handler for startup/shutdown tasks."""

    _run_migrations_if_needed()
    _bootstrap_admin_user()

    # Startup: begin background market data sync when not under pytest.
    if "pytest" not in sys.modules and not os.getenv("PYTEST_CURRENT_TEST"):
        schedule_market_data_sync()
        schedule_instrument_master_sync()
        if settings.enable_legacy_alerts:
            from .services.indicator_alerts import schedule_indicator_alerts

            schedule_indicator_alerts()
        schedule_alerts_v3()
        schedule_synthetic_gtt()

    enable_deployments = (
        (os.getenv("ST_ENABLE_DEPLOYMENTS_RUNTIME") or "").strip().lower()
    )
    allow_pytest = (
        (os.getenv("ST_ENABLE_DEPLOYMENTS_RUNTIME_UNDER_PYTEST") or "").strip().lower()
    )
    deployments_mode = (os.getenv("ST_DEPLOYMENTS_RUNTIME_MODE") or "threads").strip()
    if enable_deployments in {"1", "true", "yes", "on"} and (
        ("pytest" not in sys.modules and not os.getenv("PYTEST_CURRENT_TEST"))
        or allow_pytest in {"1", "true", "yes", "on"}
    ):
        start_deployments_runtime(mode=deployments_mode)
    yield
    # Shutdown: nothing special yet (thread is daemonised).


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    debug=settings.debug,
    lifespan=_lifespan,
)


# Best-effort: translate common broker SDK auth failures into clean API errors.
# We keep this import optional so test/lightweight environments without
# `kiteconnect` can still import the backend.
try:  # pragma: no cover - depends on optional external lib
    from kiteconnect.exceptions import (
        TokenException as KiteTokenException,  # type: ignore[import]
    )
except Exception:  # pragma: no cover - defensive
    KiteTokenException = None  # type: ignore[assignment]

if KiteTokenException is not None:  # pragma: no cover

    @app.exception_handler(KiteTokenException)  # type: ignore[arg-type]
    async def _kite_token_exception_handler(_request, exc):
        msg = str(exc)
        lowered = msg.lower()
        if "access_token" in lowered or "incorrect api_key" in lowered:
            detail = "Zerodha session is invalid or expired. Please reconnect Zerodha."
        else:
            detail = f"Zerodha authentication failed: {msg}"
        return JSONResponse(status_code=400, content={"detail": detail})


app.add_middleware(RequestContextMiddleware)
app.include_router(api_router)


__all__ = ["app"]
