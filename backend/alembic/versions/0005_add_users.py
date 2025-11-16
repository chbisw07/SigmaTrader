"""add users table

Revision ID: 0005
Revises: 0004
Create Date: 2025-11-17

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from app.core.auth import hash_password

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    # Create the table only if it does not already exist. In some
    # environments the schema may have been created via
    # Base.metadata.create_all before Alembic migrations were introduced.
    if "users" not in inspector.get_table_names():
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("username", sa.String(length=64), nullable=False),
            sa.Column("password_hash", sa.String(length=256), nullable=False),
            sa.Column(
                "role",
                sa.String(length=16),
                nullable=False,
                server_default="TRADER",
            ),
            sa.Column("display_name", sa.String(length=128), nullable=True),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint("username", name="ux_users_username"),
        )

    # Seed a default admin user with username/password "admin" if one does
    # not already exist.
    admin_password_hash = hash_password("admin")
    users_table = sa.table(
        "users",
        sa.column("id", sa.Integer()),
        sa.column("username", sa.String()),
        sa.column("password_hash", sa.String()),
        sa.column("role", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )

    existing_admin = bind.execute(
        sa.select(users_table.c.id).where(users_table.c.username == "admin"),
    ).fetchone()

    if existing_admin is None:
        op.execute(
            users_table.insert().values(
                username="admin",
                password_hash=admin_password_hash,
                role="ADMIN",
                display_name="Administrator",
                created_at=sa.func.now(),
                updated_at=sa.func.now(),
            )
        )


def downgrade() -> None:
    op.drop_table("users")
