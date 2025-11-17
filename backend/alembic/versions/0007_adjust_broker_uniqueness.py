"""adjust broker uniqueness for per-user scoping

Revision ID: 0007
Revises: 0006
Create Date: 2025-11-18

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Make broker tables user-scoped and adjust uniqueness.

    - Ensure existing global rows are associated with the admin user (if present).
    - Replace global unique constraints with per-user uniques:
      * broker_connections: UNIQUE(user_id, broker_name)
      * broker_secrets: UNIQUE(user_id, broker_name, key)
    """

    bind = op.get_bind()
    inspector = inspect(bind)

    # If users table is missing, this migration is effectively a no-op.
    if "users" not in inspector.get_table_names():
        return

    users_table = sa.table(
        "users",
        sa.column("id", sa.Integer()),
        sa.column("username", sa.String()),
    )

    admin_row = bind.execute(
        sa.select(users_table.c.id).where(users_table.c.username == "admin")
    ).fetchone()
    admin_id = admin_row[0] if admin_row is not None else None

    # Bootstrap any existing global rows to belong to the admin user so they
    # remain usable after we switch to per-user uniqueness. If there is no
    # admin row for some reason, we leave user_id as NULL.
    if admin_id is not None:
        for table_name in ("broker_connections", "broker_secrets"):
            if table_name in inspector.get_table_names():
                op.execute(
                    sa.text(
                        f"UPDATE {table_name} "
                        "SET user_id = :admin_id "
                        "WHERE user_id IS NULL"
                    ).bindparams(admin_id=admin_id)
                )

    # Adjust unique constraints to be user-scoped. Use batch_alter_table so
    # this works cleanly across SQLite and other backends.
    if "broker_connections" in inspector.get_table_names():
        with op.batch_alter_table("broker_connections", schema=None) as batch_op:
            existing_constraints = {
                uc["name"]
                for uc in inspector.get_unique_constraints("broker_connections")
            }
            if "ux_broker_connections_broker_name" in existing_constraints:
                batch_op.drop_constraint(
                    "ux_broker_connections_broker_name",
                    type_="unique",
                )
            # Create the new per-user unique if it does not already exist.
            if "ux_broker_connections_user_broker" not in existing_constraints:
                batch_op.create_unique_constraint(
                    "ux_broker_connections_user_broker",
                    ["user_id", "broker_name"],
                )

    if "broker_secrets" in inspector.get_table_names():
        with op.batch_alter_table("broker_secrets", schema=None) as batch_op:
            existing_constraints = {
                uc["name"] for uc in inspector.get_unique_constraints("broker_secrets")
            }
            if "ux_broker_secrets_broker_key" in existing_constraints:
                batch_op.drop_constraint(
                    "ux_broker_secrets_broker_key",
                    type_="unique",
                )
            if "ux_broker_secrets_user_broker_key" not in existing_constraints:
                batch_op.create_unique_constraint(
                    "ux_broker_secrets_user_broker_key",
                    ["user_id", "broker_name", "key"],
                )


def downgrade() -> None:
    inspector = inspect(op.get_bind())

    if "broker_secrets" in inspector.get_table_names():
        with op.batch_alter_table("broker_secrets", schema=None) as batch_op:
            existing_constraints = {
                uc["name"] for uc in inspector.get_unique_constraints("broker_secrets")
            }
            if "ux_broker_secrets_user_broker_key" in existing_constraints:
                batch_op.drop_constraint(
                    "ux_broker_secrets_user_broker_key",
                    type_="unique",
                )
            if "ux_broker_secrets_broker_key" not in existing_constraints:
                batch_op.create_unique_constraint(
                    "ux_broker_secrets_broker_key",
                    ["broker_name", "key"],
                )

    if "broker_connections" in inspector.get_table_names():
        with op.batch_alter_table("broker_connections", schema=None) as batch_op:
            existing_constraints = {
                uc["name"]
                for uc in inspector.get_unique_constraints("broker_connections")
            }
            if "ux_broker_connections_user_broker" in existing_constraints:
                batch_op.drop_constraint(
                    "ux_broker_connections_user_broker",
                    type_="unique",
                )
            if "ux_broker_connections_broker_name" not in existing_constraints:
                batch_op.create_unique_constraint(
                    "ux_broker_connections_broker_name",
                    ["broker_name"],
                )
