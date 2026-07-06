"""Campaign — an advertising campaign tracked by a deep-link start parameter (screen 09).

``t.me/<bot>?start=<start_param>`` attributes the user (``users.campaign_id``); regs /
trials / paid / revenue are computed from attributed users and their transactions.
``cost_minor`` is entered by the admin and feeds CPA/ROI.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base, BigInt, IntPk, TimestampMixin


class Campaign(IntPk, TimestampMixin, Base):
    __tablename__ = "campaigns"

    name: Mapped[str] = mapped_column(String(128))
    start_param: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Promo group granted to users arriving via this campaign (optional).
    promo_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("promo_groups.id", ondelete="SET NULL")
    )
    cost_minor: Mapped[int] = mapped_column(BigInt, default=0)  # ad spend, for CPA/ROI
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
