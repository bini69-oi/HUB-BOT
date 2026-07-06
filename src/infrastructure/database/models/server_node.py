"""ServerNode — local mirror of a Remnawave node (admin screen 12).

Metrics (load/users/traffic/ping/uptime/status) are refreshed by the panel sync job;
``is_for_sale`` is OUR flag — turning it off removes the node's squads from sale without
touching existing panel users.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, Enum, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.core.enums import ServerNodeStatus
from src.infrastructure.database.base import AwareDateTime, Base, BigInt, IntPk, TimestampMixin


class ServerNode(IntPk, TimestampMixin, Base):
    __tablename__ = "server_nodes"

    node_uuid: Mapped[uuid.UUID] = mapped_column(Uuid(), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    country_code: Mapped[str | None] = mapped_column(String(8))
    address: Mapped[str | None] = mapped_column(String(255))

    status: Mapped[ServerNodeStatus] = mapped_column(
        Enum(ServerNodeStatus, native_enum=False, length=16), default=ServerNodeStatus.OFFLINE
    )
    users_online: Mapped[int] = mapped_column(default=0)
    traffic_day_bytes: Mapped[int] = mapped_column(BigInt, default=0)
    load_pct: Mapped[int] = mapped_column(default=0)  # 0..100
    ping_ms: Mapped[int | None] = mapped_column()
    uptime_pct: Mapped[int | None] = mapped_column()  # 0..100

    is_for_sale: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sync_at: Mapped[dt.datetime | None] = mapped_column(AwareDateTime)
