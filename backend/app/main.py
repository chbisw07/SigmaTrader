import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError

from .api.routes import router as api_router
from .core.config import get_settings
from .core.logging import RequestContextMiddleware, configure_logging
from .db.session import SessionLocal
from .services.indicator_alerts import schedule_indicator_alerts
from .services.market_data import schedule_market_data_sync
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
            ensure_default_admin(db)
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
        schedule_indicator_alerts()
    yield
    # Shutdown: nothing special yet (thread is daemonised).


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    debug=settings.debug,
    lifespan=_lifespan,
)

app.add_middleware(RequestContextMiddleware)
app.include_router(api_router)


__all__ = ["app"]
