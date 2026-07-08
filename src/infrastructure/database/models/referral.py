"""Referral binding + earnings ledger (docs/context/04).

``referred_id`` is UNIQUE — one referrer per user. Earnings carry ``is_issued`` so a
retried webhook cannot double-pay (at-most-once, gotcha #13).
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.enums import ReferralLevel
from src.infrastructure.database.base import Base, BigInt, IntPk, TimestampMixin


class Referral(IntPk, TimestampMixin, Base):
    __tablename__ = "referrals"

    referrer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # One referrer per user.
    referred_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    level: Mapped[ReferralLevel] = mapped_column(default=ReferralLevel.FIRST)


class ReferralEarning(IntPk, TimestampMixin, Base):
    __tablename__ = "referral_earnings"
    __table_args__ = (
        # At-most-once, enforced by the DB (not just an app-level check-then-insert, which two
        # concurrent workers could both pass). One signup-days bonus per referral (#9)...
        Index(
            "uq_earning_signup_bonus",
            "referral_id",
            unique=True,
            postgresql_where=text("reason = 'signup_days_bonus'"),
            sqlite_where=text("reason = 'signup_days_bonus'"),
        ),
        # ...and one commission per (earner, source transaction), belt-and-braces with the CAS.
        Index(
            "uq_earning_txn",
            "user_id",
            "transaction_id",
            unique=True,
            postgresql_where=text("transaction_id IS NOT NULL"),
            sqlite_where=text("transaction_id IS NOT NULL"),
        ),
    )

    user_id: Mapped[int] = mapped_column(  # the earner (referrer)
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    referral_id: Mapped[int] = mapped_column(ForeignKey("referrals.id", ondelete="CASCADE"))
    amount_minor: Mapped[int] = mapped_column(BigInt)
    reason: Mapped[str | None] = mapped_column(String(64))
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL")
    )
    is_issued: Mapped[bool] = mapped_column(Boolean, default=False)
