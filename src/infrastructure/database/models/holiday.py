"""Holiday — one row of the promo calendar (admin screen 08, «Календарь акций»).

On the holiday date the scheduler broadcasts a promo; reward type/value are set by the
admin. ``results`` accumulates per-year outcomes ({"2026": {"sent": N, "conv": M}}).
Seeded with the RF holiday set; admins can toggle each row.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Enum, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.core.enums import HolidayRewardType
from src.infrastructure.database.base import Base, IntPk, JsonB, TimestampMixin


class Holiday(IntPk, TimestampMixin, Base):
    __tablename__ = "holidays"
    __table_args__ = (UniqueConstraint("month", "day", name="uq_holiday_date"),)

    month: Mapped[int] = mapped_column()  # 1..12
    day: Mapped[int] = mapped_column()  # 1..31
    name: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    reward_type: Mapped[HolidayRewardType] = mapped_column(
        Enum(HolidayRewardType, native_enum=False, length=16), default=HolidayRewardType.DISCOUNT
    )
    # Discount % / bonus days / balance minor-units — meaning depends on reward_type.
    value: Mapped[int] = mapped_column(default=0)
    send_time: Mapped[str] = mapped_column(String(5), default="10:00")  # HH:MM, MSK
    results: Mapped[dict[str, Any]] = mapped_column(JsonB, default=dict)
