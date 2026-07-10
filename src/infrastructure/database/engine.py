"""Async engine + session factory construction."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    is_sqlite = settings.database.url.startswith("sqlite")
    # hide_parameters keeps bound values (telegram ids, emails, payment ids) out of
    # str(exc) — so a DB error's text can't carry user PII into logs or telemetry.
    kwargs: dict[str, object] = {
        "pool_pre_ping": True,
        "echo": settings.app.debug,
        "hide_parameters": not settings.app.debug,
    }
    if not is_sqlite:
        kwargs["pool_size"] = settings.database.pool_size
    return create_async_engine(settings.database.url, **kwargs)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
