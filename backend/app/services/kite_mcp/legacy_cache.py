from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Dict, Iterable, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Position, PositionSnapshot, User
from app.models.holdings_summary import HoldingsSummarySnapshot
from app.models.risk_engine import EquitySnapshot
from app.schemas.ai_trading_manager import BrokerSnapshot


def _as_float(value: object, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _as_of_date_ist(now_utc: datetime) -> date:
    # IST is the market session timezone for Zerodha (India).
    try:
        from zoneinfo import ZoneInfo

        return now_utc.astimezone(ZoneInfo("Asia/Kolkata")).date()
    except Exception:
        return now_utc.date()


def _extract_margins_funds_available(margins: Dict[str, Any]) -> float | None:
    # Zerodha margins payloads vary; best-effort.
    equity = margins.get("equity") if isinstance(margins.get("equity"), dict) else {}
    available = equity.get("available") if isinstance(equity.get("available"), dict) else {}
    cash = _as_float(available.get("cash"))
    if cash is not None:
        return cash
    # Fallbacks
    return _as_float(margins.get("cash")) or _as_float(margins.get("available"))


def _extract_margins_net_equity(margins: Dict[str, Any]) -> float | None:
    equity = margins.get("equity") if isinstance(margins.get("equity"), dict) else {}
    net = _as_float(equity.get("net"))
    if net is not None:
        return net
    # Fallback to available cash if that's all we have.
    return _extract_margins_funds_available(margins)


def _compute_holdings_values(holdings: Iterable[Dict[str, Any]]) -> Tuple[int, float | None, float | None]:
    count = 0
    invested: float = 0.0
    equity_value: float = 0.0
    had_any = False
    for h in holdings:
        if not isinstance(h, dict):
            continue
        count += 1
        qty = _as_float(h.get("quantity"))
        avg = _as_float(h.get("average_price"))
        last = _as_float(h.get("last_price")) or _as_float(h.get("ltp"))
        if qty is None:
            continue
        had_any = True
        if avg is not None:
            invested += float(qty) * float(avg)
        if last is not None:
            equity_value += float(qty) * float(last)
    if not had_any:
        return count, None, None
    return count, invested, equity_value


def hydrate_legacy_caches_from_kite_mcp_snapshot(
    db: Session,
    *,
    snapshot: BrokerSnapshot,
    user: Optional[User],
) -> dict[str, Any]:
    """Populate legacy SigmaTrader cache tables from Kite MCP snapshot.

    SigmaTrader historically populates:
    - `positions` / `position_snapshots`
    - `equity_snapshots`
    - `holdings_summary_snapshots`

    When running in Kite MCP mode, we still want those tables to be filled so
    existing dashboard/views continue to show data even if KiteConnect-based
    sync jobs are not running.
    """

    now = snapshot.as_of_ts
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    as_of = _as_of_date_ist(now)

    broker_name = "zerodha"
    positions_written = 0
    position_snapshots_written = 0
    holdings_summary_written = 0
    equity_snapshot_written = 0

    # Positions cache (open positions only).
    try:
        db.query(Position).filter(Position.broker_name == broker_name).delete()
        for p in snapshot.positions:
            # Exchange is not present on BrokerPosition (MCP normalization); we
            # default to NSE for display. This keeps UI functional and avoids
            # blocking the assistant.
            db.add(
                Position(
                    broker_name=broker_name,
                    symbol=str(p.symbol or "").strip().upper(),
                    exchange="NSE",
                    product=str(p.product or "CNC").strip().upper(),
                    qty=float(p.qty or 0.0),
                    avg_price=float(p.avg_price or 0.0),
                    pnl=0.0,
                    last_updated=now,
                )
            )
            positions_written += 1

        # Daily snapshot: replace today's snapshot only (do not touch prior days).
        db.query(PositionSnapshot).filter(
            PositionSnapshot.broker_name == broker_name,
            PositionSnapshot.as_of_date == as_of,
        ).delete()

        for p in snapshot.positions:
            db.add(
                PositionSnapshot(
                    broker_name=broker_name,
                    as_of_date=as_of,
                    captured_at=now,
                    symbol=str(p.symbol or "").strip().upper(),
                    exchange="NSE",
                    product=str(p.product or "CNC").strip().upper(),
                    qty=float(p.qty or 0.0),
                    avg_price=float(p.avg_price or 0.0),
                    pnl=0.0,
                )
            )
            position_snapshots_written += 1
    except Exception:
        # Best-effort; other caches may still be usable.
        pass

    # Equity snapshot (risk engine baseline).
    try:
        if user is not None:
            net_equity = _extract_margins_net_equity(snapshot.margins or {})
            if net_equity is not None:
                row = (
                    db.query(EquitySnapshot)
                    .filter(EquitySnapshot.user_id == user.id, EquitySnapshot.as_of_date == as_of)
                    .one_or_none()
                )
                if row is None:
                    row = EquitySnapshot(
                        user_id=user.id,
                        as_of_date=as_of,
                        equity=float(net_equity),
                        peak_equity=float(net_equity),
                        drawdown_pct=0.0,
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(row)
                else:
                    row.equity = float(net_equity)
                    # Keep peak_equity monotonic.
                    row.peak_equity = max(float(row.peak_equity or 0.0), float(net_equity))
                    row.updated_at = now
                equity_snapshot_written = 1
    except Exception:
        pass

    # Holdings summary snapshot (dashboard).
    try:
        if user is not None:
            holdings_count, invested, equity_value = _compute_holdings_values(snapshot.holdings or [])
            funds = _extract_margins_funds_available(snapshot.margins or {})
            account_value = None
            if equity_value is not None and funds is not None:
                account_value = float(equity_value) + float(funds)

            row = (
                db.query(HoldingsSummarySnapshot)
                .filter(
                    HoldingsSummarySnapshot.user_id == int(user.id),
                    HoldingsSummarySnapshot.broker_name == broker_name,
                    HoldingsSummarySnapshot.as_of_date == as_of,
                )
                .one_or_none()
            )
            if row is None:
                row = HoldingsSummarySnapshot(
                    user_id=int(user.id),
                    broker_name=broker_name,
                    as_of_date=as_of,
                    captured_at=now,
                    holdings_count=int(holdings_count),
                    funds_available=funds,
                    invested=invested,
                    equity_value=equity_value,
                    account_value=account_value,
                )
                db.add(row)
            else:
                row.captured_at = now
                row.holdings_count = int(holdings_count)
                row.funds_available = funds
                row.invested = invested
                row.equity_value = equity_value
                row.account_value = account_value
            holdings_summary_written = 1
    except Exception:
        pass

    db.commit()

    return {
        "as_of_date": str(as_of),
        "broker_name": broker_name,
        "positions_written": positions_written,
        "position_snapshots_written": position_snapshots_written,
        "holdings_summary_written": holdings_summary_written,
        "equity_snapshot_written": equity_snapshot_written,
    }


__all__ = ["hydrate_legacy_caches_from_kite_mcp_snapshot"]

