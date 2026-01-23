from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Date, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime


class HoldingGoal(Base):
    __tablename__ = "holding_goals"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "broker_name",
            "symbol",
            "exchange",
            name="ux_holding_goals_scope",
        ),
        Index("ix_holding_goals_user_broker", "user_id", "broker_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    broker_name: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    exchange: Mapped[str] = mapped_column(String(16), nullable=False)

    label: Mapped[str] = mapped_column(String(24), nullable=False)
    review_date: Mapped[date] = mapped_column(Date, nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(24))
    target_value: Mapped[float | None] = mapped_column(nullable=True)
    note: Mapped[str | None] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class HoldingGoalImportPreset(Base):
    __tablename__ = "holding_goal_import_presets"

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="ux_holding_goal_import_presets"),
        Index("ix_holding_goal_import_presets_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping_json: Mapped[str] = mapped_column(String(2000), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class HoldingGoalReview(Base):
    __tablename__ = "holding_goal_reviews"

    __table_args__ = (
        Index("ix_holding_goal_reviews_user", "user_id"),
        Index("ix_holding_goal_reviews_goal", "goal_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    goal_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("holding_goals.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    broker_name: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    exchange: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    previous_review_date: Mapped[date] = mapped_column(Date, nullable=False)
    new_review_date: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )


__all__ = ["HoldingGoal", "HoldingGoalImportPreset", "HoldingGoalReview"]
