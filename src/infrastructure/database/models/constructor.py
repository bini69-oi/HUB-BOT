"""Constructor-mode pricing atoms (admin screen 03, «Конструктор» tab).

When the bot sells in constructor mode the user assembles a subscription from a period
+ optional traffic pack + extra devices, instead of picking a fixed plan. Rows here are
the editable price list; device/trial knobs live in bot-config params.
"""

from __future__ import annotations

from sqlalchemy import Boolean
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base, BigInt, IntPk, TimestampMixin


class ConstructorPeriod(IntPk, TimestampMixin, Base):
    __tablename__ = "constructor_periods"

    days: Mapped[int] = mapped_column(unique=True)  # 14/30/60/90/180/360
    price_minor: Mapped[int] = mapped_column(BigInt, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    order_index: Mapped[int] = mapped_column(default=0)


class TrafficPack(IntPk, TimestampMixin, Base):
    __tablename__ = "traffic_packs"

    gb: Mapped[int] = mapped_column(unique=True)  # 0 -> unlimited
    price_minor: Mapped[int] = mapped_column(BigInt, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    order_index: Mapped[int] = mapped_column(default=0)
