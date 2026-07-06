"""Shared helpers for the admin API: pagination, audit, serialization."""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel

from src.infrastructure.database.models.audit_log import AuditLog
from src.infrastructure.database.uow import UnitOfWork
from src.web.routes.admin.deps import AdminIdentity


class Page(BaseModel):
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


class OkOut(BaseModel):
    ok: bool = True


async def audit(
    uow: UnitOfWork,
    identity: AdminIdentity | None,
    action: str,
    entity: str | None = None,
    **payload: Any,
) -> None:
    """Append an audit entry (commit is owned by the caller)."""
    await uow.audit.add(
        AuditLog(
            actor_user_id=identity.user_id if identity else None,
            actor_label=f"@{identity.username}" if identity else "system",
            action=action,
            entity=entity,
            payload=payload,
        )
    )


def iso(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value else None


def day_bounds_utc(days_ago: int = 0) -> tuple[dt.datetime, dt.datetime]:
    """[start, end) of a UTC day ``days_ago`` days back from today."""
    today = dt.datetime.now(dt.UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - dt.timedelta(days=days_ago)
    return start, start + dt.timedelta(days=1)
