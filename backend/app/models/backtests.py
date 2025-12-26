from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    __table_args__ = (
        Index("ix_backtest_runs_owner_id", "owner_id"),
        Index("ix_backtest_runs_created_at", "created_at"),
        Index("ix_backtest_runs_kind", "kind"),
        Index("ix_backtest_runs_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )

    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")

    title: Mapped[Optional[str]] = mapped_column(String(255))

    config_json: Mapped[str] = mapped_column(Text(), nullable=False)
    result_json: Mapped[Optional[str]] = mapped_column(Text())
    error_message: Mapped[Optional[str]] = mapped_column(Text())

    started_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    finished_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


__all__ = ["BacktestRun"]
