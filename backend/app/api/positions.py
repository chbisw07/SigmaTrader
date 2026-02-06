from __future__ import annotations

import inspect
import json
from datetime import UTC, date, datetime
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user, get_current_user_optional
from app.clients import (
    AngelOneAuthError,
    AngelOneClient,
    AngelOneHttpError,
    AngelOneSession,
    ZerodhaClient,
)
from app.core.config import Settings, get_settings
from app.core.crypto import decrypt_token
from app.core.market_hours import is_preopen_now
from app.db.session import get_db
from app.models import (
    AnalyticsTrade,
    BrokerConnection,
    Order,
    Position,
    PositionSnapshot,
    User,
)
from app.schemas.positions import HoldingRead, PositionRead, PositionSnapshotRead
from app.schemas.positions_analysis import (
    ClosedTradeRead,
    MonthlyPositionsAnalyticsRead,
    PositionsAnalysisRead,
    PositionsAnalysisSummaryRead,
    SymbolPnlRead,
)
from app.services.analytics import rebuild_trades
from app.services.broker_instruments import (
    resolve_broker_symbol_and_token,
    resolve_listing_for_broker_symbol,
)
from app.services.broker_secrets import get_broker_secret
from app.services.market_data import ensure_instrument_from_holding_entry
from app.services.positions_sync import (
    sync_positions_from_angelone,
    sync_positions_from_zerodha,
)

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


def _model_validate(schema_cls, obj):
    """Compat helper for Pydantic v1/v2."""

    if hasattr(schema_cls, "model_validate"):
        return schema_cls.model_validate(obj)  # type: ignore[attr-defined]
    return schema_cls.from_orm(obj)  # type: ignore[call-arg]


def _get_zerodha_client_for_positions(
    db: Session,
    settings: Settings,
    *,
    user_id: int | None = None,
) -> ZerodhaClient:
    """Return a Zerodha client for positions sync.

    When multiple connections exist for Zerodha, we prefer the most
    recently updated one so that the last-connected account is used.
    """

    q = db.query(BrokerConnection).filter(BrokerConnection.broker_name == "zerodha")
    if user_id is not None:
        q = q.filter(BrokerConnection.user_id == user_id)
    conn = q.order_by(BrokerConnection.updated_at.desc()).first()
    if conn is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zerodha is not connected.",
        )

    api_key = get_broker_secret(
        db,
        settings,
        broker_name="zerodha",
        key="api_key",
        user_id=conn.user_id,
    )
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zerodha API key is not configured. "
            "Please configure it in the broker settings.",
        )

    try:
        from kiteconnect import KiteConnect  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="kiteconnect library is not installed in the backend environment.",
        ) from exc

    access_token = decrypt_token(settings, conn.access_token_encrypted)
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)

    return ZerodhaClient(kite)


def _get_angelone_client(
    db: Session,
    settings: Settings,
    *,
    user_id: int | None = None,
) -> AngelOneClient:
    q = db.query(BrokerConnection).filter(BrokerConnection.broker_name == "angelone")
    if user_id is not None:
        q = q.filter(BrokerConnection.user_id == user_id)
    conn = q.order_by(BrokerConnection.updated_at.desc()).first()
    if conn is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AngelOne is not connected.",
        )

    api_key = get_broker_secret(
        db,
        settings,
        broker_name="angelone",
        key="api_key",
        user_id=conn.user_id,
    )
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SmartAPI API key is not configured. "
            "Please configure it in the broker settings.",
        )

    raw = decrypt_token(settings, conn.access_token_encrypted)
    try:
        parsed = json.loads(raw) if raw else {}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"AngelOne session is invalid: {exc}",
        ) from exc

    jwt = str(parsed.get("jwt_token") or "")
    if not jwt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AngelOne session is missing jwt_token. Please reconnect.",
        )

    session = AngelOneSession(
        jwt_token=jwt,
        refresh_token=str(parsed.get("refresh_token") or "") or None,
        feed_token=str(parsed.get("feed_token") or "") or None,
        client_code=str(parsed.get("client_code") or "") or None,
    )

    client = AngelOneClient(api_key=api_key, session=session)
    client.broker_user_id = getattr(conn, "broker_user_id", None)  # type: ignore[attr-defined]
    return client


@router.post("/sync", response_model=dict)
def sync_positions(
    broker_name: Annotated[str, Query(min_length=1)] = "zerodha",
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_current_user_optional),
) -> dict:
    """Synchronize positions from a broker into the local DB cache."""

    broker = (broker_name or "").strip().lower()
    if broker == "zerodha":
        # Tests may monkeypatch `_get_zerodha_client_for_positions` with a
        # 2-arg callable (db, settings) so we only pass user_id when supported.
        try:
            sig = inspect.signature(_get_zerodha_client_for_positions)
            if "user_id" in sig.parameters:
                client = _get_zerodha_client_for_positions(
                    db,
                    settings,
                    user_id=user.id if user is not None else None,
                )
            else:
                client = _get_zerodha_client_for_positions(db, settings)
        except Exception:
            client = _get_zerodha_client_for_positions(db, settings)
        updated = sync_positions_from_zerodha(db, client)
        return {"updated": updated}
    if broker == "angelone":
        client = _get_angelone_client(
            db,
            settings,
            user_id=user.id if user is not None else None,
        )
        updated = sync_positions_from_angelone(db, client)
        return {"updated": updated}

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Positions sync not implemented for broker: {broker}",
    )


@router.get("/", response_model=List[PositionRead])
def list_positions(
    broker_name: Annotated[Optional[str], Query()] = None,
    db: Session = Depends(get_db),
) -> List[Position]:
    """Return cached positions from the local DB."""

    q = db.query(Position)
    if broker_name is not None:
        broker = (broker_name or "").strip().lower()
        q = q.filter(Position.broker_name == broker)
    return q.order_by(
        Position.symbol,
        Position.exchange,
        Position.product,
    ).all()


@router.get("/daily", response_model=List[PositionSnapshotRead])
def list_daily_positions(
    broker_name: Annotated[str, Query(min_length=1)] = "zerodha",
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    symbol: Optional[str] = None,
    include_zero: bool = True,
    db: Session = Depends(get_db),
) -> List[PositionSnapshotRead]:
    """Return daily position snapshots captured from broker positions.

    If start/end are omitted, this defaults to the latest available date.
    """

    broker = (broker_name or "").strip().lower()
    q = db.query(PositionSnapshot).filter(PositionSnapshot.broker_name == broker)

    if start_date is None and end_date is None:
        latest = (
            db.query(PositionSnapshot.as_of_date)
            .filter(PositionSnapshot.broker_name == broker)
            .order_by(PositionSnapshot.as_of_date.desc())
            .limit(1)
            .scalar()
        )
        if latest is None:
            return []
        start_date = latest
        end_date = latest

    if start_date is not None:
        q = q.filter(PositionSnapshot.as_of_date >= start_date)
    if end_date is not None:
        q = q.filter(PositionSnapshot.as_of_date <= end_date)

    if symbol:
        like = f"%{symbol.strip().upper()}%"
        q = q.filter(PositionSnapshot.symbol.like(like))

    if not include_zero:
        q = q.filter(PositionSnapshot.qty != 0)

    rows: List[PositionSnapshot] = q.order_by(
        PositionSnapshot.as_of_date.desc(),
        PositionSnapshot.symbol.asc(),
        PositionSnapshot.exchange.asc(),
        PositionSnapshot.product.asc(),
    ).all()

    out: List[PositionSnapshotRead] = []

    def _first_price(*vals: Optional[float]) -> Optional[float]:
        for v in vals:
            if v is None:
                continue
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if fv != 0:
                return fv
        return None

    for r in rows:
        # Derived: remaining qty == net qty for the snapshot.
        item = _model_validate(PositionSnapshotRead, r)
        # SQLite stores naive datetimes; interpret captured_at as UTC to ensure
        # clients can render in their local timezone (e.g. IST).
        if item.captured_at.tzinfo is None:
            item.captured_at = item.captured_at.replace(tzinfo=UTC)

        product = (r.product or "").upper()

        net_qty = float(r.qty or 0.0)
        # "Remaining" is a legacy UI column; we populate it with holdings qty
        # (when available) so users can see how much of the day started as a
        # delivery holding vs intraday activity. The canonical position size is
        # always `qty` (net qty from broker positions payload).
        if r.holding_qty is not None:
            remaining = float(r.holding_qty)
        else:
            remaining = net_qty
        # Delivery products cannot be short; clamp legacy "remaining" to 0 so
        # it doesn't imply an invalid holding size.
        if product in {"CNC", "DELIVERY"} and remaining < 0:
            remaining = 0.0
        item.remaining_qty = remaining

        day_buy_qty = float(r.day_buy_qty or 0.0)
        day_sell_qty = float(r.day_sell_qty or 0.0)
        buy_qty = float(r.buy_qty or 0.0)
        sell_qty = float(r.sell_qty or 0.0)

        if day_buy_qty > 0 and day_sell_qty > 0:
            order_type = "BOTH"
        elif day_buy_qty > 0:
            order_type = "BUY"
        elif day_sell_qty > 0:
            order_type = "SELL"
        elif net_qty < 0:
            order_type = "SHORT"
        elif net_qty > 0:
            order_type = "HOLD"
        else:
            order_type = "FLAT"
        item.order_type = order_type

        traded_qty = 0.0
        if order_type == "BUY":
            traded_qty = day_buy_qty or buy_qty or abs(float(r.qty))
        elif order_type == "SELL":
            traded_qty = day_sell_qty or sell_qty or abs(float(r.qty))
        elif order_type == "BOTH":
            traded_qty = (day_buy_qty or buy_qty) + (day_sell_qty or sell_qty)
        elif order_type == "FLAT":
            # Some brokers (notably AngelOne) return intraday buy/sell details
            # without day_* fields even when net qty is 0. Use buy/sell qty as
            # a best-effort proxy so derived metrics don't appear blank.
            if buy_qty or sell_qty:
                traded_qty = max(buy_qty, sell_qty)
        item.traded_qty = float(traded_qty or 0.0)

        avg_buy = _first_price(r.buy_avg_price, r.day_buy_avg_price)
        avg_sell = _first_price(r.sell_avg_price, r.day_sell_avg_price)
        item.avg_buy_price = avg_buy
        item.avg_sell_price = avg_sell

        ltp = r.last_price if r.last_price is not None else None
        item.ltp = float(ltp) if ltp is not None else None

        pnl_value: float | None = None
        pnl_pct: float | None = None
        today_pnl: float | None = None
        today_pnl_pct: float | None = None

        avg_price = float(r.avg_price or 0.0)
        close_price = float(r.close_price) if r.close_price is not None else None

        # Realised P&L (trade-based): (avg_sell - avg_buy) * closed_qty.
        # Show it whenever we have both averages and both buy/sell quantities.
        if avg_buy is not None and avg_sell is not None:
            qty_buy = day_buy_qty if day_buy_qty > 0 else buy_qty
            qty_sell = day_sell_qty if day_sell_qty > 0 else sell_qty
            closed_qty = min(qty_buy, qty_sell) if qty_buy > 0 and qty_sell > 0 else 0.0
            if closed_qty > 0 and float(avg_buy) != 0.0:
                pnl_value = (float(avg_sell) - float(avg_buy)) * float(closed_qty)
                pnl_pct = (pnl_value / (float(avg_buy) * float(closed_qty))) * 100.0
        pnl_qty = net_qty
        pnl_price_base = avg_price

        if product in {"CNC", "DELIVERY"} and r.holding_qty is not None:
            holding_qty = float(r.holding_qty or 0.0)
            if holding_qty != 0.0:
                pnl_qty = holding_qty
                if avg_buy is not None and avg_buy != 0:
                    pnl_price_base = float(avg_buy)

        # "Today" P&L: mark-to-market vs previous close (if available).
        if pnl_qty and item.ltp is not None and close_price:
            today_pnl = pnl_qty * (item.ltp - close_price)
            today_pnl_pct = (today_pnl / (abs(pnl_qty) * close_price)) * 100.0

        item.pnl_value = pnl_value
        item.pnl_pct = pnl_pct
        item.today_pnl = today_pnl
        item.today_pnl_pct = today_pnl_pct

        # Fallback: if we could not derive today's number (missing prices), use
        # broker-provided fields so the UI doesn't show empty cells.
        if item.today_pnl is None:
            broker_pnl = float(r.pnl or 0.0)
            item.today_pnl = (
                float(r.m2m)
                if r.m2m is not None and float(r.m2m) != 0.0
                else broker_pnl
            )

        def _pct_from_notional(
            pnl: float | None,
            *,
            qty_base: float | None,
            price_base: float | None,
        ) -> float | None:
            if pnl is None:
                return None
            if qty_base is None or qty_base <= 0:
                return None
            if price_base is None or price_base <= 0:
                return None
            notional = qty_base * price_base
            if notional <= 0:
                return None
            return (pnl / notional) * 100.0

        qty_base = abs(pnl_qty) if pnl_qty else None
        price_base = pnl_price_base if pnl_price_base else (avg_buy or avg_sell)

        if item.today_pnl_pct is None:
            item.today_pnl_pct = _pct_from_notional(
                item.today_pnl, qty_base=qty_base, price_base=price_base
            )

        out.append(item)
    return out


def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _as_float(v: object | None) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _day_window_ist(d: date) -> tuple[datetime, datetime]:
    try:
        from zoneinfo import ZoneInfo

        ist = ZoneInfo("Asia/Kolkata")
        opened = datetime(d.year, d.month, d.day, 9, 15, tzinfo=ist).astimezone(UTC)
        closed = datetime(d.year, d.month, d.day, 15, 30, tzinfo=ist).astimezone(UTC)
        return opened, closed
    except Exception:
        opened = datetime(d.year, d.month, d.day, tzinfo=UTC)
        return opened, opened


@router.get("/analysis", response_model=PositionsAnalysisRead)
def positions_analysis(
    broker_name: Annotated[str, Query(min_length=1)] = "zerodha",
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    symbol: Optional[str] = None,
    top_n: int = 10,
    db: Session = Depends(get_db),
) -> PositionsAnalysisRead:
    """Return a lightweight trading/position analytics dashboard payload.

    This is a best-effort view:
    - Closed trades are sourced from `analytics_trades` (derived from executed orders).
    - Turnover is estimated from daily position snapshots (day_buy/sell fields).
    - Open positions come from the cached `positions` table.
    """

    broker = (broker_name or "").strip().lower()
    if top_n <= 0:
        top_n = 10
    top_n = min(int(top_n), 50)

    # Determine date range defaults based on available snapshots.
    if start_date is None and end_date is None:
        latest = (
            db.query(PositionSnapshot.as_of_date)
            .filter(PositionSnapshot.broker_name == broker)
            .order_by(PositionSnapshot.as_of_date.desc())
            .limit(1)
            .scalar()
        )
        if latest is None:
            empty_summary = PositionsAnalysisSummaryRead(
                date_from=date.today(),
                date_to=date.today(),
                broker_name=broker,
            )
            return PositionsAnalysisRead(
                summary=empty_summary,
                monthly=[],
                winners=[],
                losers=[],
                open_positions=[],
                closed_trades=[],
            )
        end_date = latest
        start_date = date.fromordinal(latest.toordinal() - 30)

    assert start_date is not None
    assert end_date is not None
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    # Snapshot-based turnover aggregation (per month).
    snap_q = (
        db.query(PositionSnapshot)
        .filter(
            PositionSnapshot.broker_name == broker,
            PositionSnapshot.as_of_date >= start_date,
            PositionSnapshot.as_of_date <= end_date,
        )
        .order_by(PositionSnapshot.as_of_date.asc())
    )
    if symbol:
        like = f"%{symbol.strip().upper()}%"
        snap_q = snap_q.filter(PositionSnapshot.symbol.like(like))
    snaps: list[PositionSnapshot] = list(snap_q.all())

    monthly_turnover: dict[str, dict[str, float]] = {}
    for s in snaps:
        m = _month_key(s.as_of_date)
        entry = monthly_turnover.setdefault(
            m,
            {"buy": 0.0, "sell": 0.0},
        )
        day_buy_qty = _as_float(s.day_buy_qty)
        day_sell_qty = _as_float(s.day_sell_qty)
        buy_qty = day_buy_qty or _as_float(s.buy_qty)
        sell_qty = day_sell_qty or _as_float(s.sell_qty)

        if day_buy_qty > 0:
            buy_px = (
                _as_float(s.day_buy_avg_price)
                or _as_float(s.buy_avg_price)
                or _as_float(s.avg_price)
            )
        else:
            buy_px = _as_float(s.buy_avg_price) or _as_float(s.avg_price)
        if day_sell_qty > 0:
            sell_px = (
                _as_float(s.day_sell_avg_price)
                or _as_float(s.sell_avg_price)
                or _as_float(s.avg_price)
            )
        else:
            sell_px = _as_float(s.sell_avg_price) or _as_float(s.avg_price)

        if buy_qty > 0 and buy_px > 0:
            entry["buy"] += buy_qty * buy_px
        if sell_qty > 0 and sell_px > 0:
            entry["sell"] += sell_qty * sell_px

    # Trade-based aggregation (AnalyticsTrade joined to entry order for
    # symbol/product/broker).
    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=UTC)
    end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=UTC)
    trade_query = (
        db.query(AnalyticsTrade, Order)
        .join(Order, AnalyticsTrade.entry_order_id == Order.id)
        .filter(
            Order.broker_name == broker,
            AnalyticsTrade.closed_at >= start_dt,
            AnalyticsTrade.closed_at <= end_dt,
        )
        .order_by(AnalyticsTrade.closed_at.asc())
    )
    if symbol:
        like = f"%{symbol.strip().upper()}%"
        trade_query = trade_query.filter(Order.symbol.like(like))
    trade_rows = trade_query.all()
    if not trade_rows:
        # Best-effort: auto-rebuild analytics trades on demand so users don't
        # have to manually call the maintenance endpoint after a restart.
        try:
            rebuild_trades(db)
        except Exception:
            pass
        trade_rows = trade_query.all()

    monthly_trades: dict[str, dict[str, float | int]] = {}
    by_symbol: dict[tuple[str, str | None], dict[str, float | int]] = {}
    closed_trades: list[ClosedTradeRead] = []
    trades_pnl = 0.0
    wins_total = 0
    losses_total = 0

    trades_count = 0

    if trade_rows:
        for t, entry in trade_rows:
            closed_at = t.closed_at
            if closed_at.tzinfo is None:
                closed_at = closed_at.replace(tzinfo=UTC)
            m = f"{closed_at.year:04d}-{closed_at.month:02d}"

            bucket = monthly_trades.setdefault(
                m,
                {"pnl": 0.0, "count": 0, "wins": 0, "losses": 0},
            )
            bucket["pnl"] = float(bucket["pnl"]) + float(t.pnl)
            bucket["count"] = int(bucket["count"]) + 1
            if float(t.pnl) > 0:
                bucket["wins"] = int(bucket["wins"]) + 1
                wins_total += 1
            else:
                bucket["losses"] = int(bucket["losses"]) + 1
                losses_total += 1

            key = (entry.symbol, entry.product)
            sb = by_symbol.setdefault(key, {"pnl": 0.0, "count": 0, "wins": 0})
            sb["pnl"] = float(sb["pnl"]) + float(t.pnl)
            sb["count"] = int(sb["count"]) + 1
            if float(t.pnl) > 0:
                sb["wins"] = int(sb["wins"]) + 1

            opened_at = t.opened_at
            if opened_at.tzinfo is None:
                opened_at = opened_at.replace(tzinfo=UTC)
            closed_trades.append(
                ClosedTradeRead(
                    symbol=entry.symbol,
                    product=entry.product,
                    opened_at=opened_at,
                    closed_at=closed_at,
                    pnl=float(t.pnl),
                )
            )
            trades_pnl += float(t.pnl)
        trades_count = len(trade_rows)
    else:
        # Fallback: derive a daily closed-position P&L stream from broker
        # position snapshots. This works even when `analytics_trades` is empty
        # (common after restarts or when market order prices aren't stored).
        for s in snaps:
            product = (s.product or "").upper()
            net_qty = float(s.qty or 0.0)
            if product in {"CNC", "DELIVERY"} and net_qty < 0:
                net_qty = 0.0
            if net_qty != 0:
                continue
            buy_qty = _as_float(s.day_buy_qty) or _as_float(s.buy_qty)
            sell_qty = _as_float(s.day_sell_qty) or _as_float(s.sell_qty)
            pnl_val = (
                float(s.realised)
                if getattr(s, "realised", None) is not None
                else float(s.pnl or 0.0)
            )
            if buy_qty <= 0 and sell_qty <= 0:
                if pnl_val == 0.0:
                    continue
            if pnl_val == 0.0:
                continue
            opened_at, closed_at = _day_window_ist(s.as_of_date)
            m = _month_key(s.as_of_date)
            bucket = monthly_trades.setdefault(
                m,
                {"pnl": 0.0, "count": 0, "wins": 0, "losses": 0},
            )
            bucket["pnl"] = float(bucket["pnl"]) + float(pnl_val)
            bucket["count"] = int(bucket["count"]) + 1
            if pnl_val > 0:
                bucket["wins"] = int(bucket["wins"]) + 1
                wins_total += 1
            else:
                bucket["losses"] = int(bucket["losses"]) + 1
                losses_total += 1

            key = (str(s.symbol), str(s.product))
            sb = by_symbol.setdefault(key, {"pnl": 0.0, "count": 0, "wins": 0})
            sb["pnl"] = float(sb["pnl"]) + float(pnl_val)
            sb["count"] = int(sb["count"]) + 1
            if pnl_val > 0:
                sb["wins"] = int(sb["wins"]) + 1

            closed_trades.append(
                ClosedTradeRead(
                    symbol=str(s.symbol),
                    product=str(s.product),
                    opened_at=opened_at,
                    closed_at=closed_at,
                    pnl=float(pnl_val),
                )
            )
            trades_pnl += float(pnl_val)
        trades_count = len(closed_trades)

    # Monthly merge (turnover + trades).
    months = sorted(set(monthly_turnover.keys()) | set(monthly_trades.keys()))
    monthly_out: list[MonthlyPositionsAnalyticsRead] = []
    for m in months:
        t = monthly_trades.get(m, {"pnl": 0.0, "count": 0, "wins": 0, "losses": 0})
        tv = monthly_turnover.get(m, {"buy": 0.0, "sell": 0.0})
        count = int(t["count"])
        wins = int(t["wins"])
        losses = int(t["losses"])
        win_rate = (wins / count) if count else 0.0
        buy = float(tv["buy"])
        sell = float(tv["sell"])
        monthly_out.append(
            MonthlyPositionsAnalyticsRead(
                month=m,
                trades_pnl=float(t["pnl"]),
                trades_count=count,
                wins=wins,
                losses=losses,
                win_rate=win_rate,
                turnover_buy=buy,
                turnover_sell=sell,
                turnover_total=buy + sell,
            )
        )

    # Winners / losers by symbol based on trade PnL.
    symbols_out: list[SymbolPnlRead] = []
    for (sym, prod), agg in by_symbol.items():
        count = int(agg["count"])
        wins = int(agg["wins"])
        win_rate = (wins / count) if count else 0.0
        symbols_out.append(
            SymbolPnlRead(
                symbol=sym,
                product=prod,
                pnl=float(agg["pnl"]),
                trades=count,
                win_rate=win_rate,
            )
        )
    winners = sorted(symbols_out, key=lambda x: x.pnl, reverse=True)[:top_n]
    losers = sorted(symbols_out, key=lambda x: x.pnl)[:top_n]

    # Open positions (prefer latest daily snapshot for stability after restarts;
    # fall back to cached positions table).
    open_positions: list[PositionRead] = []
    latest_snap_date = None
    if snaps:
        latest_snap_date = max(s.as_of_date for s in snaps)
    else:
        q_latest = db.query(PositionSnapshot.as_of_date).filter(
            PositionSnapshot.broker_name == broker,
            PositionSnapshot.as_of_date <= end_date,
        )
        if symbol:
            like = f"%{symbol.strip().upper()}%"
            q_latest = q_latest.filter(PositionSnapshot.symbol.like(like))
        latest_snap_date = (
            q_latest.order_by(PositionSnapshot.as_of_date.desc()).limit(1).scalar()
        )

    if latest_snap_date is not None:
        q_open = db.query(PositionSnapshot).filter(
            PositionSnapshot.broker_name == broker,
            PositionSnapshot.as_of_date == latest_snap_date,
            PositionSnapshot.qty != 0,
        )
        if symbol:
            like = f"%{symbol.strip().upper()}%"
            q_open = q_open.filter(PositionSnapshot.symbol.like(like))
        open_snaps = q_open.order_by(
            PositionSnapshot.symbol.asc(),
            PositionSnapshot.exchange.asc(),
            PositionSnapshot.product.asc(),
        ).all()
        for s in open_snaps:
            last_updated = s.captured_at
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=UTC)
            product = (s.product or "").upper()
            net_qty = float(s.qty or 0.0)
            if product in {"CNC", "DELIVERY"} and net_qty < 0:
                net_qty = 0.0
            qty = net_qty
            if qty == 0:
                continue
            avg_price = float(s.avg_price or 0.0)
            if avg_price <= 0:
                avg_price = (
                    _as_float(s.buy_avg_price)
                    or _as_float(s.day_buy_avg_price)
                    or _as_float(s.sell_avg_price)
                    or _as_float(s.day_sell_avg_price)
                )
            open_positions.append(
                PositionRead(
                    id=int(s.id),
                    symbol=str(s.symbol),
                    exchange=str(s.exchange or "NSE"),
                    product=str(s.product),
                    qty=float(qty),
                    avg_price=float(avg_price),
                    pnl=float(s.pnl or 0.0),
                    last_updated=last_updated,
                )
            )

    if not open_positions:
        open_positions_raw: list[Position] = (
            db.query(Position)
            .filter(
                Position.broker_name == broker,
                Position.qty != 0,
            )
            .order_by(
                Position.symbol.asc(),
                Position.exchange.asc(),
                Position.product.asc(),
            )
            .all()
        )
        open_positions = [_model_validate(PositionRead, p) for p in open_positions_raw]

    summary = PositionsAnalysisSummaryRead(
        date_from=start_date,
        date_to=end_date,
        broker_name=broker,
        trades_pnl=trades_pnl,
        trades_count=trades_count,
        trades_win_rate=(
            (wins_total / (wins_total + losses_total))
            if (wins_total + losses_total)
            else 0.0
        ),
        turnover_buy=sum(v["buy"] for v in monthly_turnover.values()),
        turnover_sell=sum(v["sell"] for v in monthly_turnover.values()),
        turnover_total=sum(v["buy"] + v["sell"] for v in monthly_turnover.values()),
        open_positions_count=len(open_positions),
    )

    # Recent closed trades (most recent first; cap).
    closed_trades_sorted = sorted(
        closed_trades,
        key=lambda x: x.closed_at,
        reverse=True,
    )[: min(50, max(10, top_n * 5))]

    return PositionsAnalysisRead(
        summary=summary,
        monthly=monthly_out,
        winners=winners,
        losers=losers,
        open_positions=open_positions,
        closed_trades=closed_trades_sorted,
    )


@router.get("/holdings", response_model=List[HoldingRead])
def list_holdings(
    broker_name: Annotated[str, Query(min_length=1)] = "zerodha",
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> List[HoldingRead]:
    """Return live holdings from a broker for the current user.

    For now holdings are not cached in DB; they are fetched on-demand
    from Zerodha and projected into a simple schema that includes
    quantity, average_price, last_price, and derived P&L when possible.
    """

    broker = (broker_name or "").strip().lower()
    if broker == "angelone":
        client = _get_angelone_client(db, settings, user_id=user.id)
        try:
            raw = client.list_holdings()
        except AngelOneAuthError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "AngelOne session is invalid or expired. "
                    "Please reconnect AngelOne."
                ),
            ) from exc
        except AngelOneHttpError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"AngelOne holdings fetch failed: {exc}",
            ) from exc
        except Exception as exc:  # pragma: no cover - defensive
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"AngelOne holdings fetch failed: {exc}",
            ) from exc

        buy_orders: List[Order] = (
            db.query(Order)
            .filter(
                Order.user_id == user.id,
                Order.broker_name == "angelone",
                Order.side == "BUY",
                Order.status.in_(["EXECUTED", "PARTIALLY_EXECUTED"]),
            )
            .order_by(Order.created_at.desc())
            .all()
        )
        last_buy_by_symbol: dict[str, datetime] = {}
        for o in buy_orders:
            if o.symbol not in last_buy_by_symbol:
                last_buy_by_symbol[o.symbol] = o.created_at

        # During pre-open (09:00–09:15 IST), refresh LTP for each holding
        # because AngelOne's holdings snapshot can lag during the auction.
        ltp_map: dict[tuple[str, str], float] = {}
        if is_preopen_now():
            for entry in raw:
                if not isinstance(entry, dict):
                    continue

                broker_symbol = entry.get("tradingsymbol") or entry.get("symbol")
                exchange = entry.get("exchange") or "NSE"
                if not isinstance(broker_symbol, str) or not isinstance(exchange, str):
                    continue

                exch_u = exchange.strip().upper()
                broker_symbol_u = broker_symbol.strip().upper()
                listing = resolve_listing_for_broker_symbol(
                    db,
                    broker_name="angelone",
                    exchange=exch_u,
                    broker_symbol=broker_symbol_u,
                )
                symbol_u = (
                    listing.symbol.strip().upper()
                    if listing is not None
                    else broker_symbol_u
                )
                resolved = resolve_broker_symbol_and_token(
                    db,
                    broker_name="angelone",
                    exchange=exch_u,
                    symbol=symbol_u,
                )
                if resolved is None:
                    continue
                angel_symbol, token = resolved

                try:
                    ltp_map[(exch_u, symbol_u)] = client.get_ltp(
                        exchange=exch_u,
                        tradingsymbol=angel_symbol,
                        symboltoken=token,
                    )
                except Exception:
                    continue

        holdings: List[HoldingRead] = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue

            broker_symbol = entry.get("tradingsymbol") or entry.get("symbol")
            exchange = entry.get("exchange") or "NSE"
            qty = (
                entry.get("quantity") or entry.get("netqty") or entry.get("netQty") or 0
            )
            avg = (
                entry.get("averageprice")
                or entry.get("average_price")
                or entry.get("avgprice")
                or entry.get("avgPrice")
                or 0
            )
            last = entry.get("ltp") or entry.get("last_price") or entry.get("lastPrice")

            if not isinstance(broker_symbol, str) or not isinstance(exchange, str):
                continue

            exch_u = exchange.strip().upper()
            broker_symbol_u = broker_symbol.strip().upper()
            listing = resolve_listing_for_broker_symbol(
                db,
                broker_name="angelone",
                exchange=exch_u,
                broker_symbol=broker_symbol_u,
            )
            symbol_u = (
                listing.symbol.strip().upper()
                if listing is not None
                else broker_symbol_u
            )

            try:
                qty_f = float(qty)
                avg_f = float(avg)
                last_f = float(last) if last is not None else None
            except (TypeError, ValueError):
                continue
            if is_preopen_now():
                last_f = ltp_map.get((exch_u, symbol_u), last_f)

            pnl = None
            if last_f is not None:
                pnl = (last_f - avg_f) * qty_f

            total_pnl_percent: float | None = None
            if pnl is not None and qty_f and avg_f:
                cost = qty_f * avg_f
                if cost:
                    total_pnl_percent = (pnl / cost) * 100.0

            holdings.append(
                HoldingRead(
                    symbol=symbol_u,
                    quantity=qty_f,
                    average_price=avg_f,
                    exchange=exch_u,
                    last_price=last_f,
                    pnl=pnl,
                    last_purchase_date=last_buy_by_symbol.get(symbol_u),
                    total_pnl_percent=total_pnl_percent,
                    today_pnl_percent=None,
                )
            )

        return holdings

    if broker != "zerodha":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Holdings not implemented for broker: {broker}",
        )

    conn = (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.broker_name == broker,
            BrokerConnection.user_id == user.id,
        )
        .one_or_none()
    )
    if conn is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zerodha is not connected.",
        )

    api_key = get_broker_secret(
        db,
        settings,
        broker_name="zerodha",
        key="api_key",
        user_id=user.id,
    )
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zerodha API key is not configured. "
            "Please configure it in the broker settings.",
        )

    try:
        from kiteconnect import KiteConnect  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="kiteconnect library is not installed in the backend environment.",
        ) from exc

    access_token = decrypt_token(settings, conn.access_token_encrypted)
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    client = ZerodhaClient(kite)

    raw = client.list_holdings()

    # Refresh LTP and day-change using Kite's LTP endpoint so that the
    # Holdings page reflects near-real-time prices instead of relying
    # solely on the snapshot embedded in the holdings payload.
    instruments: list[tuple[str, str]] = []
    for entry in raw:
        symbol = entry.get("tradingsymbol")
        exchange = (entry.get("exchange") or "NSE").upper()
        if isinstance(symbol, str):
            instruments.append((exchange, symbol))

    ltp_map = (
        client.get_quote_bulk(instruments)
        if is_preopen_now()
        else client.get_ltp_bulk(instruments)
    )

    # Pre-compute the last executed BUY order date per symbol for this user so
    # that the holdings response can surface a "last purchase date" column.
    buy_orders: List[Order] = (
        db.query(Order)
        .filter(
            Order.user_id == user.id,
            Order.side == "BUY",
            Order.status.in_(["EXECUTED", "PARTIALLY_EXECUTED"]),
        )
        .order_by(Order.created_at.desc())
        .all()
    )
    last_buy_by_symbol: dict[str, datetime] = {}
    for o in buy_orders:
        symbol = o.symbol
        if symbol not in last_buy_by_symbol:
            last_buy_by_symbol[symbol] = o.created_at

    holdings: List[HoldingRead] = []

    for entry in raw:
        # Best-effort: keep market instrument mappings in sync with Zerodha
        # holdings so that historical OHLCV can be fetched for the same
        # symbols without requiring separate manual configuration.
        try:
            ensure_instrument_from_holding_entry(db, entry)
        except Exception:
            # Ignore mapping errors; holdings API should not fail because of
            # auxiliary market data maintenance.
            pass

        symbol = entry.get("tradingsymbol")
        exchange = (entry.get("exchange") or "NSE").upper()
        qty = entry.get("quantity", 0)
        # Zerodha holdings may report unsettled T1 shares separately; those are
        # part of the user's effective equity exposure and should be reflected
        # in holdings summary and portfolio valuation intraday (matches how
        # portfolio apps compute "current value" before T1 settles next day).
        t1_qty = entry.get("t1_quantity", 0)
        avg = entry.get("average_price", 0)

        ltp_info = ltp_map.get((exchange, symbol), {})
        last = ltp_info.get("last_price") or entry.get("last_price")
        day_change_pct_raw = entry.get("day_change_percentage")

        if not isinstance(symbol, str):
            continue

        try:
            qty_f = float(qty) + float(t1_qty or 0)
            avg_f = float(avg)
            last_f = float(last) if last is not None else None
        except (TypeError, ValueError):
            continue

        pnl = None
        if last_f is not None:
            pnl = (last_f - avg_f) * qty_f

        total_pnl_percent: float | None = None
        if pnl is not None and qty_f and avg_f:
            cost = qty_f * avg_f
            if cost:
                total_pnl_percent = (pnl / cost) * 100.0

        prev_close: float | None = None
        raw_prev_close = ltp_info.get("prev_close")
        if isinstance(raw_prev_close, (int, float)):
            prev_close = float(raw_prev_close)
        elif day_change_pct_raw is not None and entry.get("last_price") is not None:
            # Fallback: derive previous close from the holdings snapshot
            # using Zerodha's day_change_percentage and last_price fields.
            try:
                snap_last_f = float(entry.get("last_price"))
                pct_f = float(day_change_pct_raw)
                denom = 1.0 + pct_f / 100.0
                if snap_last_f and denom:
                    prev_close = snap_last_f / denom
            except (TypeError, ValueError, ZeroDivisionError):
                prev_close = None

        today_pnl_percent: float | None = None
        if prev_close is not None and last_f is not None and prev_close != 0:
            today_pnl_percent = (last_f - prev_close) / prev_close * 100.0
        elif day_change_pct_raw is not None:
            try:
                today_pnl_percent = float(day_change_pct_raw)
            except (TypeError, ValueError):
                today_pnl_percent = None

        last_purchase_date = last_buy_by_symbol.get(symbol)

        holdings.append(
            HoldingRead(
                symbol=symbol,
                quantity=qty_f,
                average_price=avg_f,
                exchange=exchange,
                last_price=last_f,
                pnl=pnl,
                last_purchase_date=last_purchase_date,
                total_pnl_percent=total_pnl_percent,
                today_pnl_percent=today_pnl_percent,
            )
        )

    return holdings


__all__ = ["router"]
