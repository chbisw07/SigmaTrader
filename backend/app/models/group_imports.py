from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class GroupImport(Base):
    __tablename__ = "group_imports"

    __table_args__ = (
        UniqueConstraint("group_id", name="ux_group_imports_group_id"),
        Index("ix_group_imports_group_id", "group_id"),
        Index("ix_group_imports_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
    )

    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="TRADINGVIEW",
    )
    original_filename: Mapped[Optional[str]] = mapped_column(String(255))
    file_hash: Mapped[Optional[str]] = mapped_column(String(64))

    schema_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    symbol_mapping_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    values = relationship(
        "GroupImportValue",
        back_populates="import_record",
        cascade="all,delete-orphan",
        order_by="GroupImportValue.id",
    )


class GroupImportValue(Base):
    __tablename__ = "group_import_values"

    __table_args__ = (
        UniqueConstraint(
            "import_id",
            "symbol",
            "exchange",
            name="ux_group_import_values_import_symbol_exchange",
        ),
        Index("ix_group_import_values_import_id", "import_id"),
        Index("ix_group_import_values_symbol_exchange", "symbol", "exchange"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    import_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("group_imports.id", ondelete="CASCADE"),
        nullable=False,
    )

    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False, default="NSE")
    values_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )

    import_record = relationship("GroupImport", back_populates="values")


__all__ = ["GroupImport", "GroupImportValue"]
