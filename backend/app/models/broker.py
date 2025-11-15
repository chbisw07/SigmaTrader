from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BrokerConnection(Base):
    __tablename__ = "broker_connections"

    __table_args__ = (
        UniqueConstraint(
            "broker_name",
            name="ux_broker_connections_broker_name",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    broker_name: Mapped[str] = mapped_column(String(32), nullable=False)
    access_token_encrypted: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


__all__ = ["BrokerConnection"]
