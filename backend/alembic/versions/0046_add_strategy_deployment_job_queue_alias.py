"""Alias revision for 0046_add_strategy_deployment_job_queue.

Revision "0046" exists, but some later migrations refer to the textual id
"0046_add_strategy_deployment_job_queue". This file bridges the chain without
changing already-applied revision ids in existing databases.
"""

from __future__ import annotations

revision = "0046_add_strategy_deployment_job_queue"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    return


def downgrade() -> None:
    return
