from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime


class ScreenerRun(Base):
    __tablename__ = "screener_runs"

    __table_args__ = (
        CheckConstraint(
            "status IN ('RUNNING', 'DONE', 'ERROR')",
            name="ck_screener_runs_status",
        ),
        Index("ix_screener_runs_user_created", "user_id", "created_at"),
        Index("ix_screener_runs_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="RUNNING")

    # Request metadata (for reproducibility/debugging).
    target_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    variables_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    condition_dsl: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evaluation_cadence: Mapped[str] = mapped_column(
        String(8), nullable=False, default="1m"
    )
    signal_strategy_version_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("signal_strategy_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    signal_strategy_output: Mapped[Optional[str]] = mapped_column(String(64))
    signal_strategy_params_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}"
    )

    # Progress + outcome
    total_symbols: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evaluated_symbols: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched_symbols: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_symbols: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    error: Mapped[Optional[str]] = mapped_column(Text)
    results_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

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


__all__ = ["ScreenerRun"]
