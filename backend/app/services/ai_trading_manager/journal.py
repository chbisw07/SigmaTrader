from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Dict, List
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.ai_trading_manager import (
    AiTmBrokerSnapshot,
    AiTmJournalEvent,
    AiTmJournalForecast,
    AiTmJournalPostmortem,
    AiTmPositionShadow,
)
from app.schemas.ai_trading_manager import BrokerSnapshot


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def _json_loads(raw: str, fallback: Any) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def append_journal_event(
    db: Session,
    *,
    shadow_id: str,
    ts: datetime,
    event_type: str,
    source: str,
    intent_payload: Dict[str, Any] | None = None,
    riskgate_result: Dict[str, Any] | None = None,
    playbook_result: Dict[str, Any] | None = None,
    broker_result: Dict[str, Any] | None = None,
    notes: str | None = None,
) -> AiTmJournalEvent:
    row = AiTmJournalEvent(
        event_id=uuid4().hex,
        position_shadow_id=shadow_id,
        ts=ts,
        event_type=str(event_type).upper(),
        source=str(source).upper(),
        intent_payload_json=_json_dumps(intent_payload or {}),
        riskgate_result_json=_json_dumps(riskgate_result) if riskgate_result is not None else None,
        playbook_result_json=_json_dumps(playbook_result) if playbook_result is not None else None,
        broker_result_json=_json_dumps(broker_result) if broker_result is not None else None,
        notes=notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_journal_events(
    db: Session,
    *,
    shadow_id: str,
    limit: int = 200,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    rows = (
        db.execute(
            select(AiTmJournalEvent)
            .where(AiTmJournalEvent.position_shadow_id == shadow_id)
            .order_by(desc(AiTmJournalEvent.ts))
            .offset(max(0, int(offset)))
            .limit(min(int(limit), 1000))
        )
        .scalars()
        .all()
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "event_id": r.event_id,
                "position_shadow_id": r.position_shadow_id,
                "ts": r.ts.isoformat() if r.ts else None,
                "event_type": r.event_type,
                "source": r.source,
                "intent_payload": _json_loads(r.intent_payload_json or "{}", {}),
                "riskgate_result": _json_loads(r.riskgate_result_json or "{}", {}) if r.riskgate_result_json else None,
                "playbook_result": _json_loads(r.playbook_result_json or "{}", {}) if r.playbook_result_json else None,
                "broker_result": _json_loads(r.broker_result_json or "{}", {}) if r.broker_result_json else None,
                "notes": r.notes,
            }
        )
    return out


def upsert_journal_forecast(
    db: Session,
    *,
    forecast_id: str | None,
    shadow_id: str,
    author: str = "USER",
    outlook_pct: float | None = None,
    horizon_days: int | None = None,
    confidence: int | None = None,
    rationale_tags: list[str] | None = None,
    thesis_text: str | None = None,
    invalidation_text: str | None = None,
) -> Dict[str, Any]:
    now = datetime.now(UTC)
    row = None
    if forecast_id:
        row = (
            db.execute(select(AiTmJournalForecast).where(AiTmJournalForecast.forecast_id == forecast_id))
            .scalars()
            .first()
        )
    if row is None:
        row = AiTmJournalForecast(
            forecast_id=forecast_id or uuid4().hex,
            position_shadow_id=shadow_id,
            created_at=now,
            author=str(author).upper(),
            outlook_pct=outlook_pct,
            horizon_days=horizon_days,
            confidence=confidence,
            rationale_tags_json=_json_dumps(rationale_tags or []),
            thesis_text=thesis_text,
            invalidation_text=invalidation_text,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {
            "forecast_id": row.forecast_id,
            "position_shadow_id": row.position_shadow_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "author": row.author,
            "outlook_pct": row.outlook_pct,
            "horizon_days": row.horizon_days,
            "confidence": row.confidence,
            "rationale_tags": _json_loads(row.rationale_tags_json or "[]", []),
            "thesis_text": row.thesis_text,
            "invalidation_text": row.invalidation_text,
        }

    if outlook_pct is not None:
        row.outlook_pct = outlook_pct
    if horizon_days is not None:
        row.horizon_days = horizon_days
    if confidence is not None:
        row.confidence = confidence
    if rationale_tags is not None:
        row.rationale_tags_json = _json_dumps(rationale_tags)
    if thesis_text is not None:
        row.thesis_text = thesis_text
    if invalidation_text is not None:
        row.invalidation_text = invalidation_text
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "forecast_id": row.forecast_id,
        "position_shadow_id": row.position_shadow_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "author": row.author,
        "outlook_pct": row.outlook_pct,
        "horizon_days": row.horizon_days,
        "confidence": row.confidence,
        "rationale_tags": _json_loads(row.rationale_tags_json or "[]", []),
        "thesis_text": row.thesis_text,
        "invalidation_text": row.invalidation_text,
    }


def list_journal_forecasts(
    db: Session,
    *,
    shadow_id: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    rows = (
        db.execute(
            select(AiTmJournalForecast)
            .where(AiTmJournalForecast.position_shadow_id == shadow_id)
            .order_by(desc(AiTmJournalForecast.created_at))
            .limit(min(int(limit), 200))
        )
        .scalars()
        .all()
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "forecast_id": r.forecast_id,
                "position_shadow_id": r.position_shadow_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "author": r.author,
                "outlook_pct": r.outlook_pct,
                "horizon_days": r.horizon_days,
                "confidence": r.confidence,
                "rationale_tags": _json_loads(r.rationale_tags_json or "[]", []),
                "thesis_text": r.thesis_text,
                "invalidation_text": r.invalidation_text,
            }
        )
    return out


@dataclass(frozen=True)
class PostmortemMetrics:
    mfe_abs: float | None = None
    mfe_pct: float | None = None
    mae_abs: float | None = None
    mae_pct: float | None = None
    peak_price_while_open: float | None = None


def _extract_mark_from_snapshot(
    *, snap: BrokerSnapshot, symbol: str, product: str
) -> tuple[float | None, float | None]:
    sym = symbol.strip().upper()
    prod = product.strip().upper()

    # Holdings payloads tend to include last_price and pnl.
    for h in snap.holdings or []:
        if not isinstance(h, dict):
            continue
        hs = str(h.get("tradingsymbol") or h.get("symbol") or "").strip().upper()
        if hs != sym:
            continue
        qty = float(h.get("quantity") or h.get("qty") or 0.0)
        if qty == 0:
            continue
        avg = h.get("average_price") or h.get("avg_price")
        ltp = h.get("last_price") or h.get("ltp")
        try:
            avg_f = float(avg) if avg is not None else None
            ltp_f = float(ltp) if ltp is not None else None
        except Exception:
            avg_f = None
            ltp_f = None
        if avg_f is None or ltp_f is None:
            return (ltp_f, None)
        pnl = (ltp_f - avg_f) * float(qty)
        pnl_pct = pnl / (avg_f * float(qty)) * 100.0 if avg_f and qty else None
        return (ltp_f, pnl_pct)

    # Positions payloads are normalized; fall back to quotes_cache when available.
    pos = None
    for p in snap.positions or []:
        if str(p.symbol or "").strip().upper() == sym and str(p.product or "CNC").strip().upper() == prod:
            pos = p
            break
    if pos is None or not pos.avg_price:
        return (None, None)

    qpx = None
    for q in snap.quotes_cache or []:
        if str(q.symbol or "").strip().upper() == sym:
            qpx = float(q.last_price)
            break
    if qpx is None:
        return (None, None)

    pnl = (float(qpx) - float(pos.avg_price)) * float(pos.qty or 0.0)
    base = float(pos.avg_price) * float(pos.qty or 0.0)
    pnl_pct = pnl / base * 100.0 if base else None
    return (float(qpx), pnl_pct)


def compute_postmortem_metrics(
    db: Session,
    settings: Settings,
    *,
    shadow: AiTmPositionShadow,
    closed_at: datetime,
    lookback_days_cap: int = 120,
) -> PostmortemMetrics:
    _ = settings
    # Best-effort: scan broker snapshots between first_seen_at and closed_at (capped).
    start = shadow.first_seen_at
    if not start:
        return PostmortemMetrics()

    try:
        from datetime import timedelta

        cap_start = closed_at - timedelta(days=int(lookback_days_cap))
        if start < cap_start:
            start = cap_start
    except Exception:
        pass

    rows = (
        db.execute(
            select(AiTmBrokerSnapshot)
            .where(
                AiTmBrokerSnapshot.account_id == shadow.broker_account_id,
                AiTmBrokerSnapshot.as_of_ts >= start,
                AiTmBrokerSnapshot.as_of_ts <= closed_at,
            )
            .order_by(AiTmBrokerSnapshot.as_of_ts.asc())
        )
        .scalars()
        .all()
    )
    if not rows:
        return PostmortemMetrics()

    max_pnl_pct: float | None = None
    min_pnl_pct: float | None = None
    peak_price: float | None = None

    for r in rows:
        raw = _json_loads(r.payload_json or "{}", {})
        try:
            snap = BrokerSnapshot.model_validate(raw)
        except Exception:
            continue
        px, pnl_pct = _extract_mark_from_snapshot(snap=snap, symbol=shadow.symbol, product=shadow.product)
        if px is not None:
            peak_price = max(peak_price or px, px)
        if pnl_pct is None:
            continue
        max_pnl_pct = pnl_pct if max_pnl_pct is None else max(max_pnl_pct, pnl_pct)
        min_pnl_pct = pnl_pct if min_pnl_pct is None else min(min_pnl_pct, pnl_pct)

    qty = float(shadow.qty_current or 0.0) or None
    avg = float(shadow.avg_price) if shadow.avg_price is not None else None
    mfe_abs = (max_pnl_pct / 100.0 * (avg * qty)) if (max_pnl_pct is not None and qty and avg) else None
    mae_abs = (min_pnl_pct / 100.0 * (avg * qty)) if (min_pnl_pct is not None and qty and avg) else None

    return PostmortemMetrics(
        mfe_abs=mfe_abs,
        mfe_pct=max_pnl_pct,
        mae_abs=mae_abs,
        mae_pct=min_pnl_pct,
        peak_price_while_open=peak_price,
    )


def create_postmortem_for_shadow(
    db: Session,
    settings: Settings,
    *,
    shadow: AiTmPositionShadow,
    closed_at: datetime,
) -> Dict[str, Any]:
    metrics = compute_postmortem_metrics(db, settings, shadow=shadow, closed_at=closed_at)
    realized_pnl_abs = float(shadow.pnl_abs) if shadow.pnl_abs is not None else None
    realized_pnl_pct = float(shadow.pnl_pct) if shadow.pnl_pct is not None else None

    latest_forecast = (
        db.execute(
            select(AiTmJournalForecast)
            .where(AiTmJournalForecast.position_shadow_id == shadow.shadow_id)
            .order_by(desc(AiTmJournalForecast.created_at))
            .limit(1)
        )
        .scalars()
        .first()
    )
    fva: dict[str, Any] = {}
    if latest_forecast is not None:
        fva = {
            "outlook_pct": latest_forecast.outlook_pct,
            "horizon_days": latest_forecast.horizon_days,
            "confidence": latest_forecast.confidence,
        }
        if realized_pnl_pct is not None and latest_forecast.outlook_pct is not None:
            # Basic "directional" hit/miss; avoid hindsight overreach.
            fva["directional_hit"] = (realized_pnl_pct >= 0) == (float(latest_forecast.outlook_pct) >= 0)

    row = AiTmJournalPostmortem(
        postmortem_id=uuid4().hex,
        position_shadow_id=shadow.shadow_id,
        closed_at=closed_at,
        realized_pnl_abs=realized_pnl_abs,
        realized_pnl_pct=realized_pnl_pct,
        mfe_abs=metrics.mfe_abs,
        mfe_pct=metrics.mfe_pct,
        mae_abs=metrics.mae_abs,
        mae_pct=metrics.mae_pct,
        peak_price_while_open=metrics.peak_price_while_open,
        exit_quality="UNKNOWN",
        exit_quality_explanation=None,
        forecast_vs_actual_json=_json_dumps(fva),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "postmortem_id": row.postmortem_id,
        "position_shadow_id": row.position_shadow_id,
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
        "realized_pnl_abs": row.realized_pnl_abs,
        "realized_pnl_pct": row.realized_pnl_pct,
        "mfe_abs": row.mfe_abs,
        "mfe_pct": row.mfe_pct,
        "mae_abs": row.mae_abs,
        "mae_pct": row.mae_pct,
        "peak_price_while_open": row.peak_price_while_open,
        "exit_quality": row.exit_quality,
        "exit_quality_explanation": row.exit_quality_explanation,
        "forecast_vs_actual": _json_loads(row.forecast_vs_actual_json or "{}", {}),
    }


def get_latest_postmortem(
    db: Session,
    *,
    shadow_id: str,
) -> Dict[str, Any] | None:
    row = (
        db.execute(
            select(AiTmJournalPostmortem)
            .where(AiTmJournalPostmortem.position_shadow_id == shadow_id)
            .order_by(desc(AiTmJournalPostmortem.closed_at))
            .limit(1)
        )
        .scalars()
        .first()
    )
    if row is None:
        return None
    return {
        "postmortem_id": row.postmortem_id,
        "position_shadow_id": row.position_shadow_id,
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
        "realized_pnl_abs": row.realized_pnl_abs,
        "realized_pnl_pct": row.realized_pnl_pct,
        "mfe_abs": row.mfe_abs,
        "mfe_pct": row.mfe_pct,
        "mae_abs": row.mae_abs,
        "mae_pct": row.mae_pct,
        "peak_price_while_open": row.peak_price_while_open,
        "exit_quality": row.exit_quality,
        "exit_quality_explanation": row.exit_quality_explanation,
        "forecast_vs_actual": _json_loads(row.forecast_vs_actual_json or "{}", {}),
    }


__all__ = [
    "append_journal_event",
    "create_postmortem_for_shadow",
    "get_latest_postmortem",
    "list_journal_events",
    "list_journal_forecasts",
    "upsert_journal_forecast",
]
