"""winback steps (sleeping-users return funnel)

Revision ID: e4f2c9d17a55
Revises: b71f0d2c9ad1
Create Date: 2026-07-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e4f2c9d17a55"
down_revision = "b71f0d2c9ad1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "winback_steps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("offset_days", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(length=4096), nullable=False),
        sa.Column("discount_pct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("send_time", sa.String(length=5), nullable=False, server_default="12:00"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("offset_days", name="uq_winback_offset"),
    )


def downgrade() -> None:
    op.drop_table("winback_steps")
