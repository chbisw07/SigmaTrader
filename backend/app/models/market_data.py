from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MarketInstrument(Base):
    __tablename__ = "market_instruments"

    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "exchange",
            name="ux_market_instruments_symbol_exchange",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    instrument_token: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Candle(Base):
    __tablename__ = "candles"

    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "exchange",
            "timeframe",
            "ts",
            name="ux_candles_symbol_exchange_tf_ts",
        ),
        Index(
            "ix_candles_symbol_exchange_tf_ts",
            "symbol",
            "exchange",
            "timeframe",
            "ts",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


__all__ = ["MarketInstrument", "Candle"]
