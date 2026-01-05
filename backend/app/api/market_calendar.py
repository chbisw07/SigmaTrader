from __future__ import annotations

import csv
import io
from datetime import date, time
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.market_hours import (
    DEFAULT_MARKET_CLOSE,
    DEFAULT_MARKET_OPEN,
    resolve_market_session,
)
from app.db.session import get_db
from app.models import MarketCalendar
from app.schemas.market_calendar import MarketCalendarRowRead

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()

ALLOWED_SESSION_TYPES = {"CLOSED", "SETTLEMENT_ONLY", "HALF_DAY", "SPECIAL", "NORMAL"}


def _parse_date(raw: str) -> date:
    try:
        return date.fromisoformat((raw or "").strip())
    except Exception as exc:
        raise ValueError("Invalid date; expected YYYY-MM-DD.") from exc


def _parse_time_optional(raw: str | None) -> Optional[time]:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        hh, mm = s.split(":", 1)
        return time(hour=int(hh), minute=int(mm))
    except Exception as exc:
        raise ValueError("Invalid time; expected HH:MM.") from exc


@router.get("/defaults")
def get_market_defaults() -> dict[str, str]:
    return {
        "timezone": "Asia/Kolkata",
        "market_open": (
            f"{DEFAULT_MARKET_OPEN.hour:02d}:{DEFAULT_MARKET_OPEN.minute:02d}"
        ),
        "market_close": (
            f"{DEFAULT_MARKET_CLOSE.hour:02d}:{DEFAULT_MARKET_CLOSE.minute:02d}"
        ),
    }


@router.get("/resolve")
def resolve_session_preview(
    exchange: str = Query(..., min_length=1),
    day: date = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    session = resolve_market_session(db, day=day, exchange=exchange)
    return session.as_dict()


@router.get("/", response_model=list[MarketCalendarRowRead])
def list_calendar_rows(
    exchange: str = Query(..., min_length=1),
    start: Optional[date] = Query(default=None),
    end: Optional[date] = Query(default=None),
    limit: int = Query(default=400, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> list[MarketCalendarRowRead]:
    exch = str(exchange).upper()
    q = db.query(MarketCalendar).filter(MarketCalendar.exchange == exch)
    if start is not None:
        q = q.filter(MarketCalendar.date >= start)
    if end is not None:
        q = q.filter(MarketCalendar.date <= end)
    rows = q.order_by(MarketCalendar.date.asc()).limit(int(limit)).all()
    return [
        MarketCalendarRowRead(
            date=r.date,
            exchange=r.exchange,
            session_type=r.session_type,
            open_time=r.open_time,
            close_time=r.close_time,
            notes=r.notes,
        )
        for r in rows
    ]


@router.get("/export")
def export_calendar_csv(
    exchange: str = Query(..., min_length=1),
    start: Optional[date] = Query(default=None),
    end: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    exch = str(exchange).upper()
    q = db.query(MarketCalendar).filter(MarketCalendar.exchange == exch)
    if start is not None:
        q = q.filter(MarketCalendar.date >= start)
    if end is not None:
        q = q.filter(MarketCalendar.date <= end)
    rows = q.order_by(MarketCalendar.date.asc()).all()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "exchange", "session_type", "open_time", "close_time", "notes"])
    for r in rows:
        w.writerow(
            [
                r.date.isoformat(),
                r.exchange,
                r.session_type,
                r.open_time.strftime("%H:%M") if r.open_time else "",
                r.close_time.strftime("%H:%M") if r.close_time else "",
                r.notes or "",
            ]
        )
    buf.seek(0)

    filename = f"market_calendar_{exch}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import")
async def import_calendar_csv(
    exchange: str = Query(..., min_length=1),
    csv_text: str = Body(..., media_type="text/csv"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    exch = str(exchange).upper()
    reader = csv.DictReader(io.StringIO(csv_text))
    required = {"date", "exchange", "session_type", "open_time", "close_time", "notes"}
    if not required.issubset({(h or "").strip() for h in (reader.fieldnames or [])}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV must include headers: {', '.join(sorted(required))}.",
        )

    inserted = 0
    updated = 0
    errors: list[dict[str, Any]] = []

    for i, row in enumerate(reader, start=2):  # header is row 1
        try:
            d = _parse_date(row.get("date") or "")
            row_exch = str(row.get("exchange") or "").upper()
            if row_exch and row_exch != exch:
                raise ValueError(f"exchange mismatch: expected {exch}, got {row_exch}")
            st = str(row.get("session_type") or "").upper().strip()
            if st not in ALLOWED_SESSION_TYPES:
                raise ValueError(f"invalid session_type: {st}")
            open_t = _parse_time_optional(row.get("open_time"))
            close_t = _parse_time_optional(row.get("close_time"))
            notes = (row.get("notes") or "").strip() or None

            if st in {"HALF_DAY", "SPECIAL"} and (open_t is None or close_t is None):
                raise ValueError(f"{st} requires open_time and close_time")

            entity = (
                db.query(MarketCalendar)
                .filter(MarketCalendar.date == d)
                .filter(MarketCalendar.exchange == exch)
                .one_or_none()
            )
            if entity is None:
                entity = MarketCalendar(date=d, exchange=exch)
                inserted += 1
            else:
                updated += 1

            entity.session_type = st
            entity.open_time = open_t
            entity.close_time = close_t
            entity.notes = notes
            db.add(entity)
        except Exception as exc:
            errors.append({"row": i, "error": str(exc), "data": row})

    if errors:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "CSV validation failed.", "errors": errors[:50]},
        )

    db.commit()
    return {"inserted": inserted, "updated": updated}


__all__ = ["router"]
