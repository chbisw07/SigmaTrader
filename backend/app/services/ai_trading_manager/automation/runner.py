from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Dict

from sqlalchemy import and_, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.ai_trading_manager import AiTmPlaybook, AiTmPlaybookRun
from app.services.ai_trading_manager import audit_store
from app.services.ai_trading_manager.ai_settings_config import get_ai_settings_with_source
from app.services.ai_trading_manager.broker_factory import get_broker_adapter
from app.services.ai_trading_manager.execution.engine import ExecutionEngine
from app.services.ai_trading_manager.feature_flags import require_execution_enabled
from app.services.ai_trading_manager.ledger_snapshot import build_ledger_snapshot
from app.services.ai_trading_manager.playbooks import create_playbook_run, get_trade_plan
from app.services.ai_trading_manager.riskgate.engine import evaluate_riskgate

logger = logging.getLogger(__name__)


@dataclass
class AutomationState:
    running: bool = False
    last_tick_at: datetime | None = None


_state = AutomationState()


def _dedupe_key(playbook_id: str, now: datetime, cadence_sec: int) -> str:
    window = int(now.timestamp()) // max(int(cadence_sec), 1)
    return f"{playbook_id}:{window}"


def run_automation_tick(*, max_playbooks: int = 20) -> int:
    settings = get_settings()

    now = datetime.now(UTC)
    ran = 0
    with SessionLocal() as db:
        cfg, _src = get_ai_settings_with_source(db, settings)
        if not cfg.feature_flags.monitoring_enabled:
            return 0

        due = (
            db.execute(
                select(AiTmPlaybook)
                .where(
                    and_(
                        AiTmPlaybook.enabled.is_(True),
                        AiTmPlaybook.armed.is_(True),
                        AiTmPlaybook.cadence_sec.isnot(None),
                        AiTmPlaybook.next_run_at.isnot(None),
                        AiTmPlaybook.next_run_at <= now,
                    )
                )
                .order_by(AiTmPlaybook.next_run_at)
                .limit(max_playbooks)
            )
            .scalars()
            .all()
        )

        for pb in due:
            cadence = int(pb.cadence_sec or 0)
            if cadence <= 0:
                continue
            dk = _dedupe_key(pb.playbook_id, now, cadence)
            # Dedupe: do not run the same playbook window twice.
            exists = (
                db.execute(
                    select(AiTmPlaybookRun).where(
                        AiTmPlaybookRun.playbook_id == pb.playbook_id,
                        AiTmPlaybookRun.dedupe_key == dk,
                    )
                )
                .scalars()
                .first()
            )
            if exists is not None:
                pb.next_run_at = now + timedelta(seconds=cadence)
                pb.updated_at = now
                db.commit()
                continue

            plan = get_trade_plan(db, plan_id=pb.plan_id)
            if plan is None:
                create_playbook_run(
                    db,
                    playbook_id=pb.playbook_id,
                    dedupe_key=dk,
                    decision_id=None,
                    authorization_message_id=None,
                    status="FAILED",
                    outcome={"error": "PLAYBOOK_PLAN_MISSING"},
                )
                pb.next_run_at = now + timedelta(seconds=cadence)
                pb.updated_at = now
                db.commit()
                continue

            decision = audit_store.new_decision_trace(
                correlation_id=f"auto-{pb.playbook_id}-{dk}",
                account_id=pb.account_id,
                user_message=f"automation_run:{pb.playbook_id}",
                inputs_used={"playbook_id": pb.playbook_id, "dedupe_key": dk},
            )

            adapter = get_broker_adapter(db, settings=settings, user_id=pb.user_id)
            broker_snapshot = adapter.get_snapshot(account_id=pb.account_id)
            try:
                symbols = [str(s).upper() for s in plan.intent.symbols]
                quotes = adapter.get_quotes(account_id=pb.account_id, symbols=symbols)
                broker_snapshot = broker_snapshot.model_copy(update={"quotes_cache": quotes})
            except Exception:
                pass
            ledger_snapshot = build_ledger_snapshot(db, account_id=pb.account_id)
            risk = evaluate_riskgate(
                plan=plan,
                broker=broker_snapshot,
                ledger=ledger_snapshot,
                eval_ts=broker_snapshot.as_of_ts,
            )

            decision.riskgate_result = risk.decision
            outcome: Dict[str, Any] = {
                "type": "AUTOMATION_RUN",
                "playbook_id": pb.playbook_id,
                "dedupe_key": dk,
                "risk_outcome": risk.decision.outcome.value,
                "reasons": risk.decision.reasons,
            }

            run_status = "COMPLETED"
            try:
                if risk.decision.outcome.value != "allow":
                    run_status = "VETOED"
                    outcome["execution"] = {"executed": False}
                else:
                    auth_id = str(pb.armed_by_message_id) if pb.armed_by_message_id else None
                    cfg2, _src2 = get_ai_settings_with_source(db, settings)
                    if cfg2.feature_flags.ai_execution_enabled and not cfg2.kill_switch.ai_execution_kill_switch:
                        if not auth_id:
                            run_status = "SKIPPED"
                            outcome["execution"] = {"executed": False, "reason": "ARM_AUTH_MISSING"}
                        else:
                            require_execution_enabled(db, settings)
                            engine = ExecutionEngine()
                            outcome["execution"] = engine.execute_to_broker(
                                db,
                                user_id=pb.user_id,
                                account_id=pb.account_id,
                                correlation_id=decision.correlation_id,
                                plan=plan,
                                idempotency_key=f"auto:{pb.playbook_id}:{auth_id}:{dk}",
                                broker=adapter,
                            )
                            outcome["authorization_message_id"] = auth_id
                    else:
                        engine = ExecutionEngine()
                        res = engine.dry_run_execute(
                            db,
                            user_id=pb.user_id,
                            account_id=pb.account_id,
                            correlation_id=decision.correlation_id,
                            plan=plan,
                            idempotency_key=f"auto_dry:{pb.playbook_id}:{dk}",
                        )
                        outcome["execution"] = {"mode": "dry_run", "order_intents": res.order_intents}
            except Exception as exc:
                # Execution disabled or other errors: keep auditable.
                run_status = "FAILED"
                outcome["error"] = str(exc)

            decision.final_outcome = outcome
            audit_store.persist_decision_trace(db, decision, user_id=pb.user_id)
            create_playbook_run(
                db,
                playbook_id=pb.playbook_id,
                dedupe_key=dk,
                decision_id=decision.decision_id,
                authorization_message_id=str(pb.armed_by_message_id) if pb.armed_by_message_id else None,
                status=run_status,
                outcome=outcome,
            )
            pb.last_run_at = now
            pb.next_run_at = now + timedelta(seconds=cadence)
            pb.updated_at = now
            db.commit()
            ran += 1

    return ran


def _loop() -> None:
    _state.running = True
    try:
        while True:
            _state.last_tick_at = datetime.now(UTC)
            try:
                run_automation_tick()
            except Exception:
                logger.exception("AI TM automation tick failed.")
            time.sleep(1.0)
    finally:
        _state.running = False


def schedule_ai_tm_automation() -> None:
    if _state.running:
        return
    t = threading.Thread(target=_loop, name="ai-tm-automation", daemon=True)
    t.start()


def get_automation_state() -> AutomationState:
    return _state
