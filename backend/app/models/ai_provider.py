from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime


class AiProviderKey(Base):
    __tablename__ = "ai_provider_keys"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "provider",
            "key_name",
            name="ux_ai_provider_keys_user_provider_name",
        ),
        Index("ix_ai_provider_keys_provider", "provider"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    key_name: Mapped[str] = mapped_column(String(64), nullable=False)

    # Encrypted secret (API key). Never return plaintext to clients.
    key_ciphertext: Mapped[str] = mapped_column(String(2048), nullable=False)
    # Masked representation for UI (e.g. "sk-…abcd").
    key_masked: Mapped[str] = mapped_column(String(64), nullable=False)

    # Optional provider metadata (JSON string): base_url override, org/project, etc.
    meta_json: Mapped[str | None] = mapped_column(Text())

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


__all__ = ["AiProviderKey"]

