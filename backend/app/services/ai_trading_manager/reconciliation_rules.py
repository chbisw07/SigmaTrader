from __future__ import annotations

from typing import Dict, List, Tuple

from app.schemas.ai_trading_manager import (
    BrokerSnapshot,
    LedgerSnapshot,
    ReconciliationDelta,
    ReconciliationSeverity,
)


def _pos_key(symbol: str, product: str) -> str:
    return f"{symbol}:{product}".upper()


def reconcile_positions(broker: BrokerSnapshot, ledger: LedgerSnapshot) -> List[ReconciliationDelta]:
    broker_by: Dict[str, float] = {_pos_key(p.symbol, p.product): float(p.qty) for p in broker.positions}
    ledger_by: Dict[str, float] = {
        _pos_key(p.symbol, p.product): float(p.expected_qty) for p in ledger.expected_positions
    }

    deltas: List[ReconciliationDelta] = []
    keys = sorted(set(broker_by) | set(ledger_by))
    for k in keys:
        b = broker_by.get(k)
        e = ledger_by.get(k)
        if b is None and e is not None:
            deltas.append(
                ReconciliationDelta(
                    delta_type="POSITION_MISSING_AT_BROKER",
                    severity=ReconciliationSeverity.medium,
                    key=k,
                    summary=f"Expected position {k} qty={e} missing at broker.",
                    broker_ref={},
                    expected_ref={"expected_qty": e},
                )
            )
            continue
        if b is not None and e is None:
            deltas.append(
                ReconciliationDelta(
                    delta_type="POSITION_EXTRA_AT_BROKER",
                    severity=ReconciliationSeverity.medium,
                    key=k,
                    summary=f"Broker has position {k} qty={b} not present in expected ledger.",
                    broker_ref={"qty": b},
                    expected_ref={},
                )
            )
            continue
        if b is None or e is None:
            continue
        if abs(b - e) > 1e-9:
            deltas.append(
                ReconciliationDelta(
                    delta_type="POSITION_QTY_MISMATCH",
                    severity=ReconciliationSeverity.high,
                    key=k,
                    summary=f"Position {k} qty mismatch broker={b} expected={e}.",
                    broker_ref={"qty": b},
                    expected_ref={"expected_qty": e},
                )
            )
    return deltas


def _order_key(symbol: str, side: str, product: str, qty: float) -> str:
    return f"{symbol}:{side}:{product}:{qty}".upper()


def reconcile_orders(broker: BrokerSnapshot, ledger: LedgerSnapshot) -> List[ReconciliationDelta]:
    # Phase 0: use a coarse signature to compare; Phase 1 will use broker order ids.
    broker_keys = {_order_key(o.symbol, o.side, o.product, float(o.qty)) for o in broker.orders}
    ledger_keys = {_order_key(o.symbol, o.side, o.product, float(o.qty)) for o in ledger.expected_orders}

    deltas: List[ReconciliationDelta] = []
    for k in sorted(ledger_keys - broker_keys):
        deltas.append(
            ReconciliationDelta(
                delta_type="ORDER_MISSING_AT_BROKER",
                severity=ReconciliationSeverity.low,
                key=k,
                summary=f"Expected order signature {k} missing at broker.",
                broker_ref={},
                expected_ref={"signature": k},
            )
        )
    for k in sorted(broker_keys - ledger_keys):
        deltas.append(
            ReconciliationDelta(
                delta_type="ORDER_EXTRA_AT_BROKER",
                severity=ReconciliationSeverity.low,
                key=k,
                summary=f"Broker has unexpected order signature {k}.",
                broker_ref={"signature": k},
                expected_ref={},
            )
        )
    return deltas


def reconcile(broker: BrokerSnapshot, ledger: LedgerSnapshot) -> Tuple[List[ReconciliationDelta], Dict[str, int]]:
    deltas = []
    deltas.extend(reconcile_positions(broker, ledger))
    deltas.extend(reconcile_orders(broker, ledger))
    severity_counts = {"L": 0, "M": 0, "H": 0}
    for d in deltas:
        severity_counts[d.severity.value] = severity_counts.get(d.severity.value, 0) + 1
    return deltas, severity_counts
