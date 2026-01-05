from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models import GroupMember, Position, StrategyDeployment


def _sym_key(exchange: str, symbol: str) -> str:
    return f"{(exchange or 'NSE').strip().upper()}:{(symbol or '').strip().upper()}"


def _signed_qty(*, qty: float, side: str | None = None) -> float:
    side_u = (side or "").upper()
    if side_u == "SHORT":
        return -abs(float(qty or 0.0))
    return float(qty or 0.0)


def _qty_side(qty: float) -> str:
    if qty > 0:
        return "LONG"
    if qty < 0:
        return "SHORT"
    return "FLAT"


@dataclass(frozen=True)
class ExposureSymbolSummary:
    exchange: str
    symbol: str
    broker_net_qty: float
    broker_side: str
    deployments_net_qty: float
    deployments_side: str
    combined_net_qty: float
    combined_side: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange,
            "symbol": self.symbol,
            "broker_net_qty": self.broker_net_qty,
            "broker_side": self.broker_side,
            "deployments_net_qty": self.deployments_net_qty,
            "deployments_side": self.deployments_side,
            "combined_net_qty": self.combined_net_qty,
            "combined_side": self.combined_side,
        }


def compute_deployment_exposure(
    db: Session,
    *,
    dep: StrategyDeployment,
) -> dict[str, Any]:
    """Compute a best-effort exposure summary for the deployment.

    This is used for safety warnings and direction mismatch handling. It is DB-first:
    - Live broker positions: from cached `positions` table (broker sync).
    - Deployment exposure: aggregated from state_json across deployments.
    """

    now = datetime.now(UTC)
    symbols = []
    if dep.target_kind == "SYMBOL" and dep.symbol:
        symbols = [{"exchange": dep.exchange or "NSE", "symbol": dep.symbol}]
    elif dep.target_kind == "GROUP" and dep.group_id:
        members = (
            db.query(GroupMember)
            .filter(GroupMember.group_id == int(dep.group_id))
            .all()
        )
        for m in members:
            if not m.symbol:
                continue
            symbols.append(
                {
                    "exchange": (m.exchange or "NSE").strip().upper(),
                    "symbol": (m.symbol or "").strip().upper(),
                }
            )

    sym_keys = [
        _sym_key(s["exchange"], s["symbol"]) for s in symbols if s.get("symbol")
    ]

    broker_name = str(dep.broker_name or "zerodha").strip().lower()
    broker_net_by_key: dict[str, float] = {k: 0.0 for k in sym_keys}
    if sym_keys:
        for k in sym_keys:
            exchange, symbol = k.split(":", 1)
            rows = (
                db.query(Position)
                .filter(Position.broker_name == broker_name)
                .filter(Position.exchange == exchange)
                .filter(Position.symbol == symbol)
                .all()
            )
            broker_net_by_key[k] = float(sum(float(p.qty or 0.0) for p in rows))

    # Sum open positions across deployments (paper + live; best effort).
    deployments_net_by_key: dict[str, float] = {k: 0.0 for k in sym_keys}
    if sym_keys:
        deps = (
            db.query(StrategyDeployment)
            .options(joinedload(StrategyDeployment.state))
            .filter(StrategyDeployment.owner_id == dep.owner_id)
            .filter(StrategyDeployment.broker_name == dep.broker_name)
            .filter(StrategyDeployment.execution_target == dep.execution_target)
            .all()
        )
        for d in deps:
            st = getattr(d, "state", None)
            raw_state = getattr(st, "state_json", None)
            if not raw_state:
                continue
            try:
                s = json.loads(raw_state)
            except Exception:
                continue
            pos = s.get("positions")
            if not isinstance(pos, dict):
                continue
            for key, pv in pos.items():
                if key not in deployments_net_by_key:
                    continue
                if not isinstance(pv, dict):
                    continue
                qty = float(pv.get("qty") or 0.0)
                if qty == 0:
                    continue
                side = str(pv.get("side") or "").upper() or None
                deployments_net_by_key[key] += _signed_qty(qty=qty, side=side)

    symbols_out: list[ExposureSymbolSummary] = []
    for k in sym_keys:
        exchange, symbol = k.split(":", 1)
        broker_qty = float(broker_net_by_key.get(k, 0.0))
        dep_qty = float(deployments_net_by_key.get(k, 0.0))
        combined = broker_qty + dep_qty
        symbols_out.append(
            ExposureSymbolSummary(
                exchange=exchange,
                symbol=symbol,
                broker_net_qty=broker_qty,
                broker_side=_qty_side(broker_qty),
                deployments_net_qty=dep_qty,
                deployments_side=_qty_side(dep_qty),
                combined_net_qty=combined,
                combined_side=_qty_side(combined),
            )
        )

    return {
        "as_of_utc": now.isoformat(),
        "broker_name": broker_name,
        "execution_target": str(dep.execution_target or "PAPER").upper(),
        "symbols": [s.to_dict() for s in symbols_out],
    }


def detect_direction_mismatch(
    exposure: dict[str, Any] | None,
    *,
    direction: str,
) -> list[dict[str, Any]]:
    """Return per-symbol mismatch details (empty list => no mismatch)."""

    if not exposure:
        return []
    dir_u = (direction or "").upper()
    out: list[dict[str, Any]] = []
    for s in exposure.get("symbols") or []:
        if not isinstance(s, dict):
            continue
        broker_qty = float(s.get("broker_net_qty") or 0.0)
        if broker_qty == 0:
            continue
        broker_side = _qty_side(broker_qty)
        if dir_u in {"LONG", "SHORT"} and broker_side != dir_u:
            out.append(
                {
                    "exchange": s.get("exchange"),
                    "symbol": s.get("symbol"),
                    "broker_net_qty": broker_qty,
                    "broker_side": broker_side,
                }
            )
    return out


__all__ = ["compute_deployment_exposure", "detect_direction_mismatch"]
