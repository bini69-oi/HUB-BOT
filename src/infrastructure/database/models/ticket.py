"""Ticket + TicketMessage — support conversations (admin screen 11).

A ticket belongs to a user; messages alternate between the user (via the bot) and
support (via the cabinet). Status flow: open → waiting (support replied) → closed,
reopenable.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.enums import TicketAuthor, TicketStatus
from src.infrastructure.database.base import AwareDateTime, Base, IntPk, TimestampMixin, utcnow


class Ticket(IntPk, TimestampMixin, Base):
    __tablename__ = "tickets"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subject: Mapped[str] = mapped_column(String(256))
    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus, native_enum=False, length=16),
        default=TicketStatus.OPEN,
        index=True,
    )
    closed_at: Mapped[dt.datetime | None] = mapped_column(AwareDateTime)

    messages: Mapped[list[TicketMessage]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", order_by="TicketMessage.id"
    )


class TicketMessage(IntPk, Base):
    __tablename__ = "ticket_messages"

    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    author: Mapped[TicketAuthor] = mapped_column(Enum(TicketAuthor, native_enum=False, length=8))
    text: Mapped[str] = mapped_column(String(4096))
    created_at: Mapped[dt.datetime] = mapped_column(AwareDateTime, default=utcnow)

    ticket: Mapped[Ticket] = relationship(back_populates="messages")
