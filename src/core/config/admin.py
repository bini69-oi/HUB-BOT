"""Admin cabinet settings: bootstrap credentials + session lifetime."""

from __future__ import annotations

from pydantic import BaseModel


class AdminSettings(BaseModel):
    # Bootstrap superadmin (created/updated at startup when both are set).
    username: str = ""
    password: str = ""
    # JWT session lifetime for the cabinet.
    session_ttl_hours: int = 12
