"""AuditLog — append-only journal of admin/system actions.

Feeds the dashboard «Последние события» and the maintenance operations journal.
``actor_label`` is denormalized (e.g. "@root_admin", "system") so entries survive user
deletion; ``payload`` holds action-specific details.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import AwareDateTime, Base, IntPk, JsonB, utcnow


class AuditLog(IntPk, Base):
    __tablename__ = "audit_log"

    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_label: Mapped[str] = mapped_column(String(64), default="system")
    action: Mapped[str] = mapped_column(String(64), index=True)  # e.g. "user.block"
    entity: Mapped[str | None] = mapped_column(String(64))  # e.g. "user:4210"
    payload: Mapped[dict[str, Any]] = mapped_column(JsonB, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(AwareDateTime, default=utcnow, index=True)
