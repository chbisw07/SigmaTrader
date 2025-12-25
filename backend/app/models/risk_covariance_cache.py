from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RiskCovarianceCache(Base):
    """Cached covariance matrices for risk-based rebalancing.

    We store matrices as JSON so we can reuse them across previews.
    Keyed by (universe_hash, timeframe, window_days, as_of_ts).
    """

    __tablename__ = "risk_covariance_cache"

    __table_args__ = (
        UniqueConstraint(
            "universe_hash",
            "timeframe",
            "window_days",
            "as_of_ts",
            name="ux_risk_cov_cache_key",
        ),
        Index(
            "ix_risk_cov_cache_lookup",
            "universe_hash",
            "timeframe",
            "window_days",
            "as_of_ts",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    universe_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False, default="1d")
    window_days: Mapped[int] = mapped_column(Integer, nullable=False, default=180)
    as_of_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    symbols_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    cov_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    vol_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    corr_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    observations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )


__all__ = ["RiskCovarianceCache"]
