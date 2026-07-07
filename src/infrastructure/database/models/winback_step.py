"""WinbackStep — one rung of the «sleeping users» win-back funnel (admin screen 08).

N days after a subscription expires the scheduler messages the user and grants a one-shot
``purchase_discount_pct`` (consumed by PricingService on the next purchase). ``text``
supports the ``{discount}`` placeholder.
"""

from __future__ import annotations

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base, IntPk, TimestampMixin


class WinbackStep(IntPk, TimestampMixin, Base):
    __tablename__ = "winback_steps"
    __table_args__ = (UniqueConstraint("offset_days", name="uq_winback_offset"),)

    offset_days: Mapped[int] = mapped_column()  # days AFTER expire_at
    text: Mapped[str] = mapped_column(
        String(4096),
        default="Мы скучаем! Вернитесь со скидкой {discount}% на любой тариф.",  # noqa: RUF001
    )
    discount_pct: Mapped[int] = mapped_column(default=0)  # one-shot purchase discount
    send_time: Mapped[str] = mapped_column(String(5), default="12:00")  # HH:MM, MSK
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
