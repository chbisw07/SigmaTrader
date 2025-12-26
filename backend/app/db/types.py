from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """Store datetimes as naive UTC; return them as tz-aware UTC.

    SQLite doesn't preserve timezone information; this type decorator makes
    datetime behavior deterministic across platforms by standardizing on UTC.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(  # type: ignore[override]
        self, value: Optional[datetime], dialect
    ) -> Optional[datetime]:
        if value is None:
            return None

        if value.tzinfo is None:
            return value

        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(  # type: ignore[override]
        self, value: Optional[datetime], dialect
    ) -> Optional[datetime]:
        if value is None:
            return None

        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)

        return value.astimezone(UTC)


__all__ = ["UTCDateTime"]
