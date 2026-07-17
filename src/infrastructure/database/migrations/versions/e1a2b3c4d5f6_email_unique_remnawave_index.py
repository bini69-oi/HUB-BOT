"""unique email + index subscriptions.remnawave_uuid

Revision ID: e1a2b3c4d5f6
Revises: d4f7a1c9e2b5
Create Date: 2026-07-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e1a2b3c4d5f6"
down_revision = "d4f7a1c9e2b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One account per email (prevents the concurrent check-then-insert dup). Replaces the old
    # non-unique index. Email uniqueness was NEVER enforced before, so a live shop can already
    # hold duplicate non-null emails — building the unique index on such a DB would raise and
    # brick the whole `alembic upgrade head` (web crash-loops, bot down). So first de-duplicate:
    # keep the earliest account per email, null the email on the rest (they lose only web login,
    # not the account; can re-register). Mirrors the DELETE dedup in d4f7a1c9e2b5.
    op.execute(
        """
        UPDATE users SET email = NULL, email_verified = false, password_hash = NULL
        WHERE email IS NOT NULL
          AND id NOT IN (SELECT MIN(id) FROM users WHERE email IS NOT NULL GROUP BY email)
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_users_email")
    op.create_index(
        "uq_users_email",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )
    # Hot webhook lookup: resolve a subscription by its panel uuid without a full-table scan.
    op.create_index(
        "ix_subscriptions_remnawave_uuid",
        "subscriptions",
        ["remnawave_uuid"],
        postgresql_where=sa.text("remnawave_uuid IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_subscriptions_remnawave_uuid", table_name="subscriptions")
    op.drop_index("uq_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"])
