"""Partner — a reseller/affiliate with their own deep-link code.

The owner onboards partners (screen «Партнёры»): each gets a ``code`` for a deep link
(``?start=partner_<code>``). A user who joins through it is bound to the partner's own
account, so the partner earns the standard referral commission via ``ReferralService`` —
real payouts live in the referral ledger (``ReferralEarning``), not on this row.

``markup_pct`` / ``revenue_share_pct`` / ``turnover_minor`` / ``earnings_minor`` are reserved
for a future full reseller model (partner sets own price); they are NOT populated yet, so the
admin API deliberately does not expose them. Do not read them as live figures.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base, IntPk, TimestampMixin


class Partner(IntPk, TimestampMixin, Base):
    __tablename__ = "partners"
    __table_args__ = (UniqueConstraint("code", name="uq_partner_code"),)

    name: Mapped[str] = mapped_column(String(128))
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    code: Mapped[str] = mapped_column(String(32))  # deep-link suffix: ?start=partner_<code>
    markup_pct: Mapped[int] = mapped_column(Integer, default=0)  # added on top of the base price
    revenue_share_pct: Mapped[int] = mapped_column(Integer, default=0)  # partner's cut of turnover
    turnover_minor: Mapped[int] = mapped_column(BigInteger, default=0)  # total driven
    earnings_minor: Mapped[int] = mapped_column(BigInteger, default=0)  # accrued share
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
