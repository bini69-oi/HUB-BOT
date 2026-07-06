"""SmartReminder — singleton config of the renewal-reminder mailing (admin screen 08).

The scheduler job reads this row daily and messages users whose subscription expires in
one of ``days_before`` (CSV, e.g. "3,1"). ``text`` supports the ``{days}`` placeholder.
"""

from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base, IntPk, TimestampMixin


class SmartReminder(IntPk, TimestampMixin, Base):
    __tablename__ = "smart_reminder"

    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    days_before: Mapped[str] = mapped_column(String(32), default="3,1")  # CSV of day offsets
    send_time: Mapped[str] = mapped_column(String(5), default="12:00")  # HH:MM, MSK
    text: Mapped[str] = mapped_column(
        String(4096), default="Ваша подписка истекает через {days} дн."
    )
    button_enabled: Mapped[bool] = mapped_column(Boolean, default=True)  # «Продлить» → mini-app
