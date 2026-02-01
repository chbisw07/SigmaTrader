from __future__ import annotations

# NOTE: These constants are the single source of truth for:
# - DB CHECK constraints (models + Alembic)
# - Backend validation (schemas/services)
# - Frontend typing (later)

# Subscription status
HOLDING_EXIT_STATUSES: tuple[str, ...] = (
    "ACTIVE",
    "PAUSED",
    "TRIGGERED_PENDING",
    "ORDER_CREATED",
    "COMPLETED",
    "ERROR",
)

# Trigger kinds
HOLDING_EXIT_TRIGGER_KINDS: tuple[str, ...] = (
    # MVP
    "TARGET_ABS_PRICE",
    "TARGET_PCT_FROM_AVG_BUY",
    # Phase 2 (kept in the enum so DB is forward-friendly)
    "DRAWDOWN_ABS_PRICE",
    "DRAWDOWN_PCT_FROM_PEAK",
)

# Sizing
HOLDING_EXIT_SIZE_MODES: tuple[str, ...] = ("ABS_QTY", "PCT_OF_POSITION")

# Execution knobs
HOLDING_EXIT_PRICE_SOURCES: tuple[str, ...] = ("LTP",)
HOLDING_EXIT_ORDER_TYPES: tuple[str, ...] = ("MARKET",)
HOLDING_EXIT_DISPATCH_MODES: tuple[str, ...] = ("MANUAL", "AUTO")
HOLDING_EXIT_EXECUTION_TARGETS: tuple[str, ...] = ("LIVE", "PAPER")

# Event types (append-only audit log)
HOLDING_EXIT_EVENT_TYPES: tuple[str, ...] = (
    "SUB_CREATED",
    "SUB_UPDATED",
    "SUB_PAUSED",
    "SUB_RESUMED",
    "EVAL",
    "EVAL_SKIPPED_MISSING_QUOTE",
    "EVAL_SKIPPED_BROKER_UNAVAILABLE",
    "TRIGGER_MET",
    "ORDER_CREATED",
    "ORDER_DISPATCHED",
    "ORDER_FAILED",
    "EXIT_QUEUED_DUE_TO_PENDING_EXIT",
    "SUB_COMPLETED",
    "SUB_ERROR",
)


def sql_in(values: tuple[str, ...]) -> str:
    """Return SQL suitable for CHECK constraints like: `col IN (...)`.

    We keep this tiny helper here so model constraints and Alembic migrations
    stay consistent without copying long string literals around.
    """

    items = ",".join([f"'{v}'" for v in values])
    return f"({items})"


__all__ = [
    "HOLDING_EXIT_STATUSES",
    "HOLDING_EXIT_TRIGGER_KINDS",
    "HOLDING_EXIT_SIZE_MODES",
    "HOLDING_EXIT_PRICE_SOURCES",
    "HOLDING_EXIT_ORDER_TYPES",
    "HOLDING_EXIT_DISPATCH_MODES",
    "HOLDING_EXIT_EXECUTION_TARGETS",
    "HOLDING_EXIT_EVENT_TYPES",
    "sql_in",
]

