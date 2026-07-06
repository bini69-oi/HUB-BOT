"""BotConfigValue — a single overridden bot-config parameter (hot-reload settings).

The *catalog* of parameters (key, category, type, default, RU/EN names, secret flag)
lives in code — ``src/core/config_registry.py`` — so adding a parameter never needs a
migration. This table stores only the values an admin has changed; the settings screen
merges registry + overrides. Secret values are Fernet-encrypted at rest (same
``APP__CRYPT_KEY`` box as gateway credentials).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base, IntPk, JsonB, TimestampMixin


class BotConfigValue(IntPk, TimestampMixin, Base):
    __tablename__ = "bot_config_values"

    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # JSON scalar (bool/int/str). Secrets are stored as Fernet tokens (str).
    value: Mapped[Any] = mapped_column(JsonB)
