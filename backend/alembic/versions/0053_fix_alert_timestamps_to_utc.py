"""Fix alert timestamps stored as IST-naive in UTC columns.

Revision ID: 0053
Revises: 0052
Create Date: 2026-01-16
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

IST_OFFSET = timedelta(hours=5, minutes=30)


def _has_table(inspector, table: str) -> bool:
    try:
        return table in inspector.get_table_names()
    except Exception:
        return False


def _has_column(inspector, table: str, name: str) -> bool:
    try:
        cols = inspector.get_columns(table)
    except Exception:
        return False
    return any(c.get("name") == name for c in cols)


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:  # pragma: no cover - defensive
            return None
    else:  # pragma: no cover - defensive
        try:
            dt = datetime.fromisoformat(str(value))
        except ValueError:
            return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def _shift_table_column(
    conn: sa.engine.Connection,
    *,
    table: str,
    pk: str,
    column: str,
    delta: timedelta,
) -> None:
    rows = conn.execute(
        sa.text(f"SELECT {pk}, {column} FROM {table} WHERE {column} IS NOT NULL")
    ).fetchall()
    if not rows:
        return
    for row in rows:
        row_id = row[0]
        raw = row[1]
        dt = _parse_dt(raw)
        if dt is None:
            continue
        conn.execute(
            sa.text(f"UPDATE {table} SET {column} = :v WHERE {pk} = :id"),
            {"v": dt + delta, "id": row_id},
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    conn = bind

    # These columns were historically written using IST-naive datetimes even
    # though they're stored using UTCDateTime (naive UTC at rest). Convert them
    # from IST-naive to UTC-naive by subtracting IST offset.
    targets: dict[str, list[str]] = {
        "alert_events": ["triggered_at"],
        "alert_definitions": ["last_evaluated_at", "last_triggered_at", "expires_at"],
        "indicator_rules": ["last_evaluated_at", "last_triggered_at", "expires_at"],
    }

    for table, columns in targets.items():
        if not _has_table(inspector, table):
            continue
        for col in columns:
            if not _has_column(inspector, table, col):
                continue
            _shift_table_column(
                conn,
                table=table,
                pk="id",
                column=col,
                delta=-IST_OFFSET,
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    conn = bind

    targets: dict[str, list[str]] = {
        "alert_events": ["triggered_at"],
        "alert_definitions": ["last_evaluated_at", "last_triggered_at", "expires_at"],
        "indicator_rules": ["last_evaluated_at", "last_triggered_at", "expires_at"],
    }

    for table, columns in targets.items():
        if not _has_table(inspector, table):
            continue
        for col in columns:
            if not _has_column(inspector, table, col):
                continue
            _shift_table_column(
                conn,
                table=table,
                pk="id",
                column=col,
                delta=IST_OFFSET,
            )
