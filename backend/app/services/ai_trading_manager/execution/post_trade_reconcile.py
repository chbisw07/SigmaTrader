from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.ai_trading_manager import audit_store
from app.services.ai_trading_manager.ledger_snapshot import build_ledger_snapshot
from app.services.ai_trading_manager.reconciler import run_reconciler
from app.services.kite_mcp.snapshot import fetch_kite_mcp_snapshot


async def post_trade_reconcile(
    db: Session,
    settings: Settings,
    *,
    account_id: str,
    user_id: Optional[int],
) -> Dict[str, Any]:
    """Fetch broker-truth snapshot, reconcile, and open exceptions (best-effort)."""

    broker_snapshot = await fetch_kite_mcp_snapshot(db, settings, account_id=account_id)
    ledger_snapshot = build_ledger_snapshot(db, account_id=account_id)

    broker_row = audit_store.persist_broker_snapshot(db, broker_snapshot, user_id=user_id)
    ledger_row = audit_store.persist_ledger_snapshot(db, ledger_snapshot, user_id=user_id)

    result = run_reconciler(broker=broker_snapshot, ledger=ledger_snapshot)
    run_row = audit_store.persist_reconciliation_run(
        db,
        user_id=user_id,
        account_id=account_id,
        broker_snapshot_id=broker_row.id,
        ledger_snapshot_id=ledger_row.id,
        deltas=result.deltas,
    )
    audit_store.open_exceptions_for_deltas(
        db,
        user_id=user_id,
        account_id=account_id,
        run_id=run_row.run_id,
        deltas=result.deltas,
    )

    return {
        "run_id": run_row.run_id,
        "delta_count": len(result.deltas),
        "severity_counts": result.severity_counts,
        "broker_snapshot_id": broker_row.id,
        "ledger_snapshot_id": ledger_row.id,
    }


__all__ = ["post_trade_reconcile"]

