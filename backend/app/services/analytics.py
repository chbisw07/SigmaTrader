from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.models import AnalyticsTrade, Order


@dataclass
class TradePair:
    entry_order_id: int
    exit_order_id: int
    strategy_id: Optional[int]
    opened_at: datetime
    closed_at: datetime
    pnl: float


def _iter_order_pairs(orders: Sequence[Order]) -> Iterable[TradePair]:
    """Yield simple entry/exit pairs for a list of executed orders.

    This v1 implementation pairs orders in a FIFO manner on a per
    (strategy_id, symbol, product) stream, assuming:
    - Each trade is a single BUY order followed by a single SELL
      (or vice versa) with equal quantity.
    - More complex patterns (partial fills, scaling) are not yet
    handled and will be ignored.
    """

    by_key: dict[Tuple[Optional[int], str, Optional[str]], List[Order]] = {}

    for order in orders:
        key = (order.strategy_id, order.symbol, order.product)
        by_key.setdefault(key, []).append(order)

    for _key, group in by_key.items():
        # Orders are expected to be pre-sorted by created_at.
        open_order: Optional[Order] = None

        for order in group:
            if open_order is None:
                open_order = order
                continue

            # Look for opposite side with equal quantity.
            if (
                open_order.side != order.side
                and open_order.qty == order.qty
                and open_order.price is not None
                and order.price is not None
            ):
                # BUY then SELL → long trade
                if open_order.side.upper() == "BUY":
                    pnl = (order.price - open_order.price) * order.qty
                else:
                    # SELL then BUY → short trade
                    pnl = (open_order.price - order.price) * order.qty

                yield TradePair(
                    entry_order_id=open_order.id,
                    exit_order_id=order.id,
                    strategy_id=open_order.strategy_id,
                    opened_at=open_order.created_at,
                    closed_at=order.created_at,
                    pnl=pnl,
                )
                open_order = None
            else:
                # Reset pairing if sequence does not match the simple model.
                open_order = order


def rebuild_trades(db: Session, strategy_id: Optional[int] = None) -> int:
    """Rebuild analytics_trades from executed orders.

    This function is idempotent and only creates trades for orders that
    are not already referenced as entry/exit in the analytics_trades
    table. It is intentionally conservative and supports only the simple
    entry/exit pairing described in `_iter_order_pairs`.
    """

    # Determine which orders are already referenced.
    existing: List[AnalyticsTrade] = db.query(AnalyticsTrade).all()
    used_order_ids: set[int] = set()
    for t in existing:
        used_order_ids.add(t.entry_order_id)
        used_order_ids.add(t.exit_order_id)

    query = db.query(Order).filter(
        Order.status == "EXECUTED",
        Order.simulated.is_(False),
    )
    if strategy_id is not None:
        query = query.filter(Order.strategy_id == strategy_id)

    orders: List[Order] = (
        query.filter(~Order.id.in_(used_order_ids))  # type: ignore[arg-type]
        .order_by(Order.strategy_id, Order.symbol, Order.product, Order.created_at)
        .all()
    )

    created = 0
    for pair in _iter_order_pairs(orders):
        trade = AnalyticsTrade(
            entry_order_id=pair.entry_order_id,
            exit_order_id=pair.exit_order_id,
            strategy_id=pair.strategy_id,
            pnl=pair.pnl,
            r_multiple=None,
            opened_at=pair.opened_at,
            closed_at=pair.closed_at,
        )
        db.add(trade)
        created += 1

    if created:
        db.commit()

    return created


@dataclass
class StrategyAnalytics:
    strategy_id: Optional[int]
    total_pnl: float
    trades: int
    win_rate: float
    avg_win: Optional[float]
    avg_loss: Optional[float]
    max_drawdown: float


def compute_strategy_analytics(
    db: Session,
    strategy_id: Optional[int] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    user_id: Optional[int] = None,
    include_simulated: bool = False,
) -> StrategyAnalytics:
    """Compute basic P&L analytics for a strategy over a date range."""

    query = db.query(AnalyticsTrade)
    if user_id is not None:
        query = query.join(Order, AnalyticsTrade.entry_order_id == Order.id)
        query = query.filter(
            (Order.user_id == user_id) | (Order.user_id.is_(None)),
        )
        if not include_simulated:
            query = query.filter(Order.simulated.is_(False))
    if strategy_id is not None:
        query = query.filter(AnalyticsTrade.strategy_id == strategy_id)
    if date_from is not None:
        query = query.filter(AnalyticsTrade.closed_at >= date_from)
    if date_to is not None:
        query = query.filter(AnalyticsTrade.closed_at <= date_to)

    trades: List[AnalyticsTrade] = query.order_by(AnalyticsTrade.closed_at).all()

    total_pnl = sum(t.pnl for t in trades)
    count = len(trades)

    wins = [t.pnl for t in trades if t.pnl > 0]
    losses = [t.pnl for t in trades if t.pnl <= 0]

    win_rate = (len(wins) / count) if count else 0.0
    avg_win = sum(wins) / len(wins) if wins else None
    avg_loss = sum(losses) / len(losses) if losses else None

    # Compute max drawdown on cumulative P&L.
    max_peak = 0.0
    max_dd = 0.0
    cumulative = 0.0
    for t in trades:
        cumulative += t.pnl
        if cumulative > max_peak:
            max_peak = cumulative
        dd = max_peak - cumulative
        if dd > max_dd:
            max_dd = dd

    return StrategyAnalytics(
        strategy_id=strategy_id,
        total_pnl=total_pnl,
        trades=count,
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        max_drawdown=max_dd,
    )


__all__ = ["rebuild_trades", "compute_strategy_analytics", "StrategyAnalytics"]
