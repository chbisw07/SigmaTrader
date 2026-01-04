from __future__ import annotations

import json
from datetime import UTC, datetime
from threading import Event, Lock, Thread
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.db.session import SessionLocal
from app.models import Order, StrategyDeployment
from app.services.deployment_jobs import record_action
from app.services.system_events import record_system_event

_reconciler_started = False
_reconciler_stop_event = Event()
_reconciler_lock = Lock()


def _json_load(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        val = json.loads(raw)
    except Exception:
        return {}
    return val if isinstance(val, dict) else {}


def _json_dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


def reconcile_deployment_once(
    db: Session,
    *,
    deployment_id: int,
    now: datetime | None = None,
) -> bool:
    """Best-effort reconciliation for PAPER deployments.

    This ensures `strategy_deployment_states.state_json` is consistent with
    the executed orders attributed to the deployment.
    """

    ts = now or datetime.now(UTC)
    dep: StrategyDeployment | None = (
        db.query(StrategyDeployment)
        .options(joinedload(StrategyDeployment.state))
        .filter(StrategyDeployment.id == deployment_id)
        .one_or_none()
    )
    if dep is None or dep.state is None:
        return False

    payload = _json_load(dep.config_json)
    cfg = payload.get("config") or {}
    exec_target = str(
        cfg.get("execution_target") or dep.execution_target or "PAPER"
    ).upper()
    if exec_target != "PAPER":
        return False

    state = _json_load(dep.state.state_json)
    positions = state.get("positions")
    if not isinstance(positions, dict):
        positions = {}
        state["positions"] = positions

    orders: list[Order] = (
        db.query(Order)
        .filter(Order.deployment_id == dep.id)
        .filter(Order.execution_target == "PAPER")
        .filter(Order.status == "EXECUTED")
        .order_by(Order.id)
        .all()
    )

    derived: dict[str, dict[str, Any]] = {}
    for o in orders:
        exchange = str(o.exchange or "NSE").upper()
        symbol = str(o.symbol or "").upper()
        if not symbol:
            continue
        key = f"{exchange}:{symbol}"
        rec = derived.setdefault(key, {"qty": 0, "side": "LONG"})
        qty = int(float(o.qty or 0))
        if o.side.upper() == "BUY":
            rec["qty"] += qty
        else:
            rec["qty"] -= qty

    mismatch = False
    for key, rec in derived.items():
        want = int(rec.get("qty") or 0)
        existing = positions.get(key)
        have = (
            int((existing or {}).get("qty") or 0) if isinstance(existing, dict) else 0
        )
        if want != have:
            mismatch = True
            break

    if not mismatch:
        return False

    # Overwrite only quantities and ensure no negative qty remains in paper model.
    new_positions: dict[str, Any] = {}
    for key, rec in derived.items():
        qty = int(rec.get("qty") or 0)
        if qty <= 0:
            continue
        new_positions[key] = {
            "qty": qty,
            "side": "LONG",
            "reconciled_at": ts.isoformat(),
        }

    state["positions"] = new_positions
    dep.state.state_json = _json_dump(state)
    dep.state.last_error = "Reconciled state from orders (mismatch detected)."
    dep.state.status = "PAUSED"
    dep.state.updated_at = ts
    db.add(dep.state)

    action = record_action(
        db,
        deployment_id=dep.id,
        job_id=None,
        kind="RECONCILE",
        payload={"positions": new_positions},
    )
    action.payload_json = _json_dump(
        {"reason": "orders_mismatch", "positions": new_positions}
    )
    db.add(action)

    db.commit()

    record_system_event(
        db,
        level="WARNING",
        category="deployments",
        message="Deployment state reconciled (orders mismatch)",
        details={"deployment_id": dep.id},
    )
    return True


def _reconciler_loop() -> None:  # pragma: no cover - background thread
    while not _reconciler_stop_event.is_set():
        with SessionLocal() as db:
            deps = (
                db.query(StrategyDeployment.id)
                .filter(StrategyDeployment.enabled.is_(True))
                .order_by(StrategyDeployment.id)
                .all()
            )
            for (dep_id,) in deps:
                try:
                    reconcile_deployment_once(db, deployment_id=int(dep_id))
                except Exception:
                    db.rollback()
        _reconciler_stop_event.wait(timeout=30.0)


def schedule_deployment_reconciler() -> None:
    global _reconciler_started
    with _reconciler_lock:
        if _reconciler_started:
            return
        _reconciler_started = True
    thread = Thread(target=_reconciler_loop, name="deployment-reconciler", daemon=True)
    thread.start()


__all__ = ["reconcile_deployment_once", "schedule_deployment_reconciler"]
