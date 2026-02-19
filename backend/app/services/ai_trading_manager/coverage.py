from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.ai.safety.safe_summary_registry import hash_identifier
from app.core.config import Settings
from app.models.ai_trading_manager import AiTmBrokerSnapshot, AiTmManagePlaybook, AiTmPositionShadow
from app.schemas.ai_trading_manager import BrokerSnapshot


def _json_loads(raw: str, fallback: Any) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _holding_rows(snapshot: BrokerSnapshot) -> List[Dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for h in snapshot.holdings or []:
        if not isinstance(h, dict):
            continue
        sym = str(h.get("tradingsymbol") or h.get("symbol") or "").strip().upper()
        if not sym:
            continue
        qty = _as_float(h.get("quantity")) or _as_float(h.get("qty")) or 0.0
        if qty == 0:
            continue
        avg = _as_float(h.get("average_price")) or _as_float(h.get("avg_price"))
        ltp = _as_float(h.get("last_price")) or _as_float(h.get("ltp"))
        invested = float(qty) * float(avg or 0.0) if avg is not None else None
        current = float(qty) * float(ltp or 0.0) if ltp is not None else None
        pnl = _as_float(h.get("pnl"))
        if pnl is None and invested is not None and current is not None:
            pnl = current - invested
        pnl_pct = (float(pnl) / float(invested) * 100.0) if invested and pnl is not None else None
        out.append(
            {
                "symbol": sym,
                "product": "CNC",
                "qty": float(qty),
                "avg": float(avg) if avg is not None else None,
                "ltp": float(ltp) if ltp is not None else None,
                "pnl_abs": float(pnl) if pnl is not None else None,
                "pnl_pct": float(pnl_pct) if pnl_pct is not None else None,
                "instrument_token": h.get("instrument_token") or h.get("instrument_id"),
                "kind": "holding",
            }
        )
    return out


def _position_rows(snapshot: BrokerSnapshot) -> List[Dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in snapshot.positions or []:
        sym = str(getattr(p, "symbol", "") or "").strip().upper()
        if not sym:
            continue
        qty = float(getattr(p, "qty", 0.0) or 0.0)
        if qty == 0:
            continue
        prod = str(getattr(p, "product", "") or "CNC").strip().upper()
        avg = getattr(p, "avg_price", None)
        out.append(
            {
                "symbol": sym,
                "product": prod,
                "qty": float(qty),
                "avg": float(avg) if isinstance(avg, (int, float)) else None,
                "ltp": None,
                "pnl_abs": None,
                "pnl_pct": None,
                "instrument_token": None,
                "kind": "position",
            }
        )
    return out


@dataclass(frozen=True)
class CoverageSyncResult:
    created: int
    updated: int
    closed: int
    open_total: int
    unmanaged_open: int
    as_of_ts: str


def _best_playbook_for_shadow(
    db: Session, *, shadow: AiTmPositionShadow
) -> Optional[AiTmManagePlaybook]:
    # Precedence: POSITION -> SYMBOL -> PORTFOLIO_DEFAULT (enabled only).
    stmt = select(AiTmManagePlaybook).where(AiTmManagePlaybook.enabled.is_(True))
    rows = db.execute(stmt).scalars().all()
    pos: AiTmManagePlaybook | None = None
    sym: AiTmManagePlaybook | None = None
    default: AiTmManagePlaybook | None = None
    for r in rows:
        st = str(r.scope_type or "").upper()
        if st == "POSITION" and str(r.scope_key or "") == str(shadow.shadow_id):
            pos = r
        if st == "SYMBOL" and str(r.scope_key or "").upper() == str(shadow.symbol or "").upper():
            sym = r
        if st == "PORTFOLIO_DEFAULT" and (r.scope_key is None or str(r.scope_key or "").strip() == ""):
            default = r
    return pos or sym or default


def sync_position_shadows_from_snapshot(
    db: Session,
    settings: Settings,
    *,
    snapshot: BrokerSnapshot,
    user_id: int | None,
) -> CoverageSyncResult:
    now = snapshot.as_of_ts or datetime.now(UTC)
    account = str(snapshot.account_id or "default")
    rows = _holding_rows(snapshot) + _position_rows(snapshot)

    seen: set[str] = set()
    created = 0
    updated = 0
    for r in rows:
        symbol = str(r.get("symbol") or "").upper()
        product = str(r.get("product") or "CNC").upper()
        kind = str(r.get("kind") or "position")
        raw_key = f"{kind}:{account}:{symbol}:{product}:LONG"
        key_hash = hash_identifier(settings, raw_key)
        seen.add(key_hash)

        instrument_id = r.get("instrument_token")
        inst_hash = hash_identifier(settings, str(instrument_id)) if instrument_id else None

        existing = db.execute(
            select(AiTmPositionShadow).where(
                AiTmPositionShadow.broker_account_id == account,
                AiTmPositionShadow.broker_position_key_hash == key_hash,
            )
        ).scalar_one_or_none()

        if existing is None:
            shadow = AiTmPositionShadow(
                shadow_id=uuid4().hex,
                broker_account_id=account,
                symbol=symbol,
                product=product,
                side="LONG",
                qty_current=float(r.get("qty") or 0.0),
                avg_price=r.get("avg"),
                first_seen_at=now,
                last_seen_at=now,
                source="BROKER_DIRECT" if str(snapshot.source or "") == "kite_mcp" else "UNKNOWN",
                status="OPEN",
                st_trade_id=None,
                broker_position_key_hash=key_hash,
                broker_instrument_id_hash=inst_hash,
                ltp=r.get("ltp"),
                pnl_abs=r.get("pnl_abs"),
                pnl_pct=r.get("pnl_pct"),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db.add(shadow)
            created += 1
            continue

        existing.qty_current = float(r.get("qty") or 0.0)
        existing.avg_price = r.get("avg")
        existing.last_seen_at = now
        existing.broker_instrument_id_hash = existing.broker_instrument_id_hash or inst_hash
        existing.ltp = r.get("ltp")
        existing.pnl_abs = r.get("pnl_abs")
        existing.pnl_pct = r.get("pnl_pct")
        if existing.status != "OPEN":
            existing.status = "OPEN"
        updated += 1

    # Close any open shadows not present in this snapshot.
    closed = 0
    open_rows = db.execute(
        select(AiTmPositionShadow).where(
            AiTmPositionShadow.broker_account_id == account,
            AiTmPositionShadow.status == "OPEN",
        )
    ).scalars().all()
    for s in open_rows:
        if s.broker_position_key_hash and s.broker_position_key_hash not in seen:
            s.status = "CLOSED"
            s.qty_current = 0.0
            s.last_seen_at = now
            closed += 1

    db.commit()

    # Compute unmanaged open count.
    open_rows2 = db.execute(
        select(AiTmPositionShadow).where(
            AiTmPositionShadow.broker_account_id == account,
            AiTmPositionShadow.status == "OPEN",
        )
    ).scalars().all()
    unmanaged = 0
    for s in open_rows2:
        pb = _best_playbook_for_shadow(db, shadow=s)
        if pb is None:
            unmanaged += 1

    return CoverageSyncResult(
        created=created,
        updated=updated,
        closed=closed,
        open_total=len(open_rows2),
        unmanaged_open=unmanaged,
        as_of_ts=now.isoformat(),
    )


def sync_position_shadows_from_latest_snapshot(
    db: Session,
    settings: Settings,
    *,
    account_id: str = "default",
    user_id: int | None,
) -> CoverageSyncResult | None:
    row = (
        db.execute(
            select(AiTmBrokerSnapshot)
            .where(AiTmBrokerSnapshot.account_id == account_id)
            .order_by(desc(AiTmBrokerSnapshot.as_of_ts))
            .limit(1)
        )
        .scalars()
        .first()
    )
    if row is None:
        return None
    raw = _json_loads(row.payload_json or "{}", {})
    try:
        snap = BrokerSnapshot.model_validate(raw)
    except Exception:
        return None
    return sync_position_shadows_from_snapshot(db, settings, snapshot=snap, user_id=user_id)


def list_position_shadows(
    db: Session,
    *,
    account_id: str = "default",
    status: str | None = "OPEN",
    unmanaged_only: bool = False,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    stmt = select(AiTmPositionShadow).where(AiTmPositionShadow.broker_account_id == account_id)
    if status:
        stmt = stmt.where(AiTmPositionShadow.status == status)
    stmt = stmt.order_by(desc(AiTmPositionShadow.last_seen_at)).limit(min(int(limit), 1000))
    rows = db.execute(stmt).scalars().all()
    out: list[dict[str, Any]] = []
    for s in rows:
        pb = _best_playbook_for_shadow(db, shadow=s)
        if unmanaged_only and pb is not None:
            continue
        out.append(
            {
                "shadow_id": s.shadow_id,
                "account_id": s.broker_account_id,
                "symbol": s.symbol,
                "product": s.product,
                "side": s.side,
                "qty_current": s.qty_current,
                "avg_price": s.avg_price,
                "ltp": s.ltp,
                "pnl_abs": s.pnl_abs,
                "pnl_pct": s.pnl_pct,
                "source": s.source,
                "status": s.status,
                "first_seen_at": s.first_seen_at.isoformat() if s.first_seen_at else None,
                "last_seen_at": s.last_seen_at.isoformat() if s.last_seen_at else None,
                "managed": bool(pb is not None),
                "playbook_id": pb.playbook_id if pb is not None else None,
                "playbook_mode": pb.mode if pb is not None else None,
                "playbook_horizon": pb.horizon if pb is not None else None,
            }
        )
    return out


def get_unmanaged_count(db: Session, *, account_id: str = "default") -> Dict[str, int]:
    rows = db.execute(
        select(AiTmPositionShadow).where(
            AiTmPositionShadow.broker_account_id == account_id,
            AiTmPositionShadow.status == "OPEN",
        )
    ).scalars().all()
    unmanaged = 0
    for s in rows:
        if _best_playbook_for_shadow(db, shadow=s) is None:
            unmanaged += 1
    return {"open_total": len(rows), "unmanaged_open": unmanaged}


__all__ = [
    "CoverageSyncResult",
    "get_unmanaged_count",
    "list_position_shadows",
    "sync_position_shadows_from_latest_snapshot",
    "sync_position_shadows_from_snapshot",
]
