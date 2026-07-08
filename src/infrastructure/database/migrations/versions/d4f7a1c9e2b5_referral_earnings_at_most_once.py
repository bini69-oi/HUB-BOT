"""referral earnings at-most-once (partial unique indexes)

Revision ID: d4f7a1c9e2b5
Revises: c1e4a8b2d6f9
Create Date: 2026-07-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d4f7a1c9e2b5"
down_revision = "c1e4a8b2d6f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # De-duplicate rows the pre-DB-constraint check-then-insert race could have created, keeping
    # the earliest (MIN id) per group, so the unique indexes can be built on any existing shop.
    op.execute(
        """
        DELETE FROM referral_earnings a USING referral_earnings b
        WHERE a.reason = 'signup_days_bonus' AND b.reason = 'signup_days_bonus'
          AND a.referral_id = b.referral_id AND a.id > b.id
        """
    )
    op.execute(
        """
        DELETE FROM referral_earnings a USING referral_earnings b
        WHERE a.transaction_id IS NOT NULL AND b.transaction_id IS NOT NULL
          AND a.user_id = b.user_id AND a.transaction_id = b.transaction_id AND a.id > b.id
        """
    )
    op.create_index(
        "uq_earning_signup_bonus",
        "referral_earnings",
        ["referral_id"],
        unique=True,
        postgresql_where=sa.text("reason = 'signup_days_bonus'"),
    )
    op.create_index(
        "uq_earning_txn",
        "referral_earnings",
        ["user_id", "transaction_id"],
        unique=True,
        postgresql_where=sa.text("transaction_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_earning_txn", table_name="referral_earnings")
    op.drop_index("uq_earning_signup_bonus", table_name="referral_earnings")
