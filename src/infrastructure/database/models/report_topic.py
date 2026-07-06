"""ReportTopic — routing of bot reports into forum-group topics (admin screen 14).

The support/report group id lives in bot-config (``REPORT_GROUP_ID``); each row binds a
report kind to a topic id + schedule. Seeded with the fixed set of kinds; admins edit
topic ids, schedules and toggles.
"""

from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base, BigInt, IntPk, TimestampMixin


class ReportTopic(IntPk, TimestampMixin, Base):
    __tablename__ = "report_topics"

    # Stable kind code: daily_report / backups / payments / tickets / alerts /
    # weekly_report / registrations.
    code: Mapped[str] = mapped_column(String(32), unique=True)
    topic_id: Mapped[int | None] = mapped_column(BigInt)  # forum topic (thread) id
    schedule: Mapped[str | None] = mapped_column(String(64))  # human schedule, e.g. "21:00"
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
