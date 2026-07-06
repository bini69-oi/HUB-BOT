"""Admin: hot-reload bot settings (screen 13) — registry + overrides."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.application.services.bot_config import BotConfigError, category_sections
from src.infrastructure.di import AppContainer
from src.web.deps import get_container
from src.web.routes.admin._common import audit
from src.web.routes.admin.deps import AdminIdentity, require_admin

router = APIRouter(prefix="/settings")


@router.get("")
async def list_settings(
    q: str = Query("", max_length=64),
    category: str = Query("", max_length=16),
    lang: str = Query("ru", pattern="^(ru|en)$"),
    container: AppContainer = Depends(get_container),
) -> dict[str, Any]:
    async with container.uow() as uow:
        rows = await container.bot_config.listing(uow, lang=lang)
    if category:
        rows = [r for r in rows if r["category"] == category]
    if q:
        needle = q.lower()
        rows = [
            r
            for r in rows
            if needle in r["key"].lower()
            or needle in r["name"].lower()
            or needle in r["description"].lower()
        ]
    return {
        "categories": category_sections(lang),
        "params": rows,
        "total": len(rows),
    }


class PatchIn(BaseModel):
    changes: dict[str, Any]


@router.patch("")
async def patch_settings(
    body: PatchIn,
    identity: AdminIdentity = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, Any]:
    if not body.changes:
        raise HTTPException(400, "no changes")
    async with container.uow() as uow:
        try:
            written = await container.bot_config.set_values(uow, body.changes)
        except BotConfigError as exc:
            raise HTTPException(400, str(exc)) from exc
        await audit(uow, identity, "settings.patch", None, keys=written)
        await uow.commit()
    return {"ok": True, "applied": written}


class ResetIn(BaseModel):
    keys: list[str]


@router.post("/reset")
async def reset_settings(
    body: ResetIn,
    identity: AdminIdentity = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, Any]:
    async with container.uow() as uow:
        await container.bot_config.reset(uow, body.keys)
        await audit(uow, identity, "settings.reset", None, keys=body.keys)
        await uow.commit()
    return {"ok": True}
