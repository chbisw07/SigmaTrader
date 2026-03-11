"""Merge orders.sent_at branch into mainline.

This repository historically had two Alembic heads:
 - Mainline migrations continuing from 0079+
 - A separate branch (7bb039b9943c) adding orders.sent_at

Some local/dev databases were stamped at revision "0081" without the corresponding
revision file committed, causing:
    Can't locate revision identified by '0081'

This revision restores "0081" as a merge point so Alembic can compute an upgrade
path on all environments.

Revision ID: 0081
Revises: 0079, 7bb039b9943c
Create Date: 2026-03-08
"""

from __future__ import annotations

from alembic import op  # noqa: F401

revision = "0081"
down_revision = ("0079", "7bb039b9943c")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Merge revision only; no schema changes.
    pass


def downgrade() -> None:
    # Downgrading a merge leaves both branches as heads.
    pass

