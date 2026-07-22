"""External sign-in identities linked to a user — one row per (provider, account).

Login via VK/Yandex/Google resolves the user through this table first and only then
falls back to the verified e-mail, because a VK account may carry no e-mail at all.
The same table powers the cabinet's «связанные аккаунты» screen: a user can hold
several identities (VK + Yandex + e-mail + Telegram) that all open one account.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base, IntPk, TimestampMixin


class LinkedAccount(IntPk, TimestampMixin, Base):
    __tablename__ = "linked_accounts"
    __table_args__ = (
        # One external account opens exactly one local user — never two.
        UniqueConstraint("provider", "external_id", name="uq_linked_provider_external"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(128))
    email: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(128))
