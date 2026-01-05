from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    Index,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime


class MarketCalendar(Base):
    __tablename__ = "market_calendar"

    __table_args__ = (
        UniqueConstraint("date", "exchange", name="ux_market_calendar_date_exchange"),
        CheckConstraint(
            "session_type IN ("
            "'NORMAL','CLOSED','SETTLEMENT_ONLY','HALF_DAY','SPECIAL'"
            ")",
            name="ck_market_calendar_session_type",
        ),
        Index("ix_market_calendar_exchange_date", "exchange", "date"),
        Index("ix_market_calendar_date", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date(), nullable=False)
    exchange: Mapped[str] = mapped_column(String(16), nullable=False)

    session_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="NORMAL"
    )
    open_time: Mapped[Optional[time]] = mapped_column(Time())
    close_time: Mapped[Optional[time]] = mapped_column(Time())
    notes: Mapped[Optional[str]] = mapped_column(Text())

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


__all__ = ["MarketCalendar"]
