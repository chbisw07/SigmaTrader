from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.ai_trading_manager.ai_settings_config import get_ai_settings_with_source
from app.services.ai_trading_manager.coverage import sync_position_shadows_from_latest_snapshot
from app.services.ai_trading_manager.manage_playbook_reviews import run_manage_playbook_reviews

logger = logging.getLogger(__name__)


@dataclass
class SchedulerState:
    running: bool = False
    last_tick_at: datetime | None = None
    last_coverage_sync_at: datetime | None = None
    last_playbook_review_at: datetime | None = None


_state = SchedulerState()


def _loop() -> None:
    settings = get_settings()
    logger.info(
        "AI TM monitoring scheduler started",
        extra={"extra": {"monitoring_enabled": True}},
    )
    _state.running = True
    try:
        while True:
            with SessionLocal() as db:
                cfg, _src = get_ai_settings_with_source(db, settings)
                enabled = bool(cfg.feature_flags.monitoring_enabled)
                kite_enabled = bool(cfg.feature_flags.kite_mcp_enabled)
            if not enabled:
                _state.last_tick_at = datetime.now(UTC)
                time.sleep(1.0)
                continue
            _state.last_tick_at = datetime.now(UTC)
            # Coverage engine runs periodically to surface broker-direct positions
            # as "unmanaged" (deterministic; uses latest stored snapshot).
            try:
                now = datetime.now(UTC)
                last = _state.last_coverage_sync_at
                if kite_enabled and (last is None or (now - last).total_seconds() >= 900):
                    with SessionLocal() as db2:
                        sync_position_shadows_from_latest_snapshot(
                            db2,
                            settings,
                            account_id="default",
                            user_id=None,
                        )
                    _state.last_coverage_sync_at = now
            except Exception:
                logger.exception("AI TM coverage sync tick failed.")

            # Playbook reviews (deterministic; proposals only).
            try:
                now2 = datetime.now(UTC)
                last2 = _state.last_playbook_review_at
                if last2 is None or (now2 - last2).total_seconds() >= 60:
                    with SessionLocal() as db3:
                        run_manage_playbook_reviews(db3, settings, account_id="default")
                    _state.last_playbook_review_at = now2
            except Exception:
                logger.exception("AI TM playbook review tick failed.")

            time.sleep(1.0)
    finally:
        _state.running = False
        logger.info("AI TM monitoring scheduler stopped")


def schedule_ai_tm_monitoring() -> None:
    if _state.running:
        return
    t = threading.Thread(target=_loop, name="ai-tm-monitoring", daemon=True)
    t.start()


def get_scheduler_state() -> SchedulerState:
    return _state
