from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime


class TradingViewAlertPayloadTemplate(Base):
    __tablename__ = "tradingview_alert_payload_templates"

    __table_args__ = (
        UniqueConstraint("name", name="ux_tradingview_alert_payload_templates_name"),
        Index(
            "ix_tradingview_alert_payload_templates_updated_at",
            "updated_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


__all__ = ["TradingViewAlertPayloadTemplate"]

