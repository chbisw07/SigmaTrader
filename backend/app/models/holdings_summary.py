from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Optional

from sqlalchemy import (
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime


class HoldingsSummarySnapshot(Base):
    __tablename__ = "holdings_summary_snapshots"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "broker_name",
            "as_of_date",
            name="ux_holdings_summary_snapshots_user_broker_date",
        ),
        Index(
            "ix_holdings_summary_snapshots_broker_date",
            "broker_name",
            "as_of_date",
        ),
        Index(
            "ix_holdings_summary_snapshots_user_date",
            "user_id",
            "as_of_date",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    broker_name: Mapped[str] = mapped_column(String(32), nullable=False, default="zerodha")
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)

    captured_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )

    holdings_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    funds_available: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    invested: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    equity_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    account_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    total_pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    today_pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    overall_win_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    today_win_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    alpha_annual_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    beta: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    cagr_1y_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cagr_2y_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cagr_1y_coverage_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cagr_2y_coverage_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    benchmark_symbol: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    benchmark_exchange: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    risk_free_rate_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


__all__ = ["HoldingsSummarySnapshot"]

