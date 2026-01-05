"""Alias revision for 0045_add_strategy_deployments.

Revision "0045" exists, but some later migrations refer to the textual id
"0045_add_strategy_deployments". This file bridges the chain without changing
already-applied revision ids in existing databases.
"""

from __future__ import annotations

revision = "0045_add_strategy_deployments"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    return


def downgrade() -> None:
    return
