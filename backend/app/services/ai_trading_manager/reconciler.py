from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from app.schemas.ai_trading_manager import BrokerSnapshot, LedgerSnapshot, ReconciliationDelta

from .reconciliation_rules import reconcile


@dataclass(frozen=True)
class ReconciliationResult:
    deltas: List[ReconciliationDelta]
    severity_counts: Dict[str, int]


def run_reconciler(*, broker: BrokerSnapshot, ledger: LedgerSnapshot) -> ReconciliationResult:
    deltas, severity_counts = reconcile(broker, ledger)
    # Deterministic ordering for UI and audit.
    deltas.sort(key=lambda d: (d.severity.value, d.delta_type, d.key))
    return ReconciliationResult(deltas=deltas, severity_counts=severity_counts)

