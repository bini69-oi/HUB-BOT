"""Admin: mini-app customization (screen 06) — template choice + branding."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from src.infrastructure.di import AppContainer
from src.web.deps import get_container
from src.web.routes.admin._common import audit, iso
from src.web.routes.admin.deps import AdminIdentity, require_admin

router = APIRouter(prefix="/miniapp")

# Template ids must match miniapp/templates.json (extended with the 8 design themes).
KNOWN_TEMPLATES = (
    "minimal",
    "private",
    "buddy",
    "native",
    "terminal",
    "magazine",
    "neon",
    "pop",
)


def _serialize(cfg: Any) -> dict[str, Any]:
    return {
        "template": cfg.template,
        "title": cfg.title,
        "greeting": cfg.greeting,
        "accent_color": cfg.accent_color,
        "photo_scale_pct": cfg.photo_scale_pct,
        "cover_path": cfg.cover_path,
        "published_at": iso(cfg.published_at),
        "templates": list(KNOWN_TEMPLATES),
    }


@router.get("")
async def get_miniapp(container: AppContainer = Depends(get_container)) -> dict[str, Any]:
    async with container.uow() as uow:
        cfg = await uow.miniapp.get_or_create()
        await uow.commit()
    return _serialize(cfg)


class MiniappPatch(BaseModel):
    template: str | None = None
    title: str | None = Field(None, max_length=64)
    greeting: str | None = Field(None, max_length=256)
    accent_color: str | None = Field(None, max_length=9)
    photo_scale_pct: int | None = Field(None, ge=70, le=130)

    @field_validator("template")
    @classmethod
    def _known(cls, v: str | None) -> str | None:
        if v is not None and v not in KNOWN_TEMPLATES:
            raise ValueError(f"unknown template: {v}")
        return v

    @field_validator("accent_color")
    @classmethod
    def _hex(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not (v.startswith("#") and len(v) in (4, 7)):
            raise ValueError("accent must be #RGB or #RRGGBB")
        return v


@router.patch("")
async def patch_miniapp(
    body: MiniappPatch,
    identity: AdminIdentity = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(400, "no changes")
    async with container.uow() as uow:
        cfg = await uow.miniapp.get_or_create()
        for key, value in data.items():
            setattr(cfg, key, value)
        await audit(uow, identity, "miniapp.patch", None, **data)
        await uow.commit()
        return _serialize(cfg)


@router.post("/publish")
async def publish_miniapp(
    identity: AdminIdentity = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, Any]:
    async with container.uow() as uow:
        cfg = await uow.miniapp.get_or_create()
        cfg.published_at = dt.datetime.now(dt.UTC)
        await audit(uow, identity, "miniapp.publish", None, template=cfg.template)
        await uow.commit()
        return _serialize(cfg)
