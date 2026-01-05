"""Alias revision for 0044_repair_backtest_runs.

This project historically had a migration file named `0044_repair_backtest_runs.py`
but its actual Alembic revision id was `0044` (not `0044_repair_backtest_runs`).

Later migrations reference `down_revision = "0044_repair_backtest_runs"`, which
breaks `alembic upgrade head` with a KeyError when this alias revision is missing.

This migration is a no-op bridge:
0043_add_backtest_runs -> 0044 -> 0044_repair_backtest_runs -> 0045...
"""

from __future__ import annotations

revision = "0044_repair_backtest_runs"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No-op: the actual repair work lives in revision "0044".
    return


def downgrade() -> None:
    # No-op.
    return
