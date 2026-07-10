"""Admin: train the AI support — knowledge base, key, model + a live Test button.

Reads/writes the AI_SUPPORT_* config keys (secrets stay encrypted) and runs a single
Claude round-trip against a sample question so the owner can see the AI answer before
turning it on for real tickets.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.application.services.bot_config import BotConfigError
from src.infrastructure.di import AppContainer
from src.infrastructure.services.ai_support import DEFAULT_KB, DEFAULT_MODEL
from src.web.deps import get_container
from src.web.routes.admin._common import audit
from src.web.routes.admin.deps import AdminIdentity, require_admin

router = APIRouter(prefix="/ai-support")


@router.get("")
async def get_ai_support(container: AppContainer = Depends(get_container)) -> dict[str, Any]:
    async with container.uow() as uow:
        v = container.bot_config.value
        key = str(await v(uow, "AI_SUPPORT_API_KEY") or "")
        return {
            "enabled": bool(await v(uow, "AI_SUPPORT_ENABLED")),
            "has_key": bool(key.strip()),
            "model": str(await v(uow, "AI_SUPPORT_MODEL") or "") or DEFAULT_MODEL,
            "knowledge_base": str(await v(uow, "AI_SUPPORT_KNOWLEDGE_BASE") or ""),
            "extra_prompt": str(await v(uow, "AI_SUPPORT_EXTRA_PROMPT") or ""),
            "default_kb": DEFAULT_KB,  # so the editor can prefill the built-in knowledge base
        }


class AiPatchIn(BaseModel):
    enabled: bool | None = None
    api_key: str | None = None  # masked "••••••••" round-trips unchanged (bot_config handles it)
    model: str | None = None
    knowledge_base: str | None = Field(None, max_length=20_000)
    extra_prompt: str | None = Field(None, max_length=4_000)


@router.patch("")
async def patch_ai_support(
    body: AiPatchIn,
    identity: AdminIdentity = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    if body.enabled is not None:
        changes["AI_SUPPORT_ENABLED"] = body.enabled
    if body.api_key is not None:
        changes["AI_SUPPORT_API_KEY"] = body.api_key
    if body.model is not None:
        changes["AI_SUPPORT_MODEL"] = body.model.strip() or DEFAULT_MODEL
    if body.knowledge_base is not None:
        changes["AI_SUPPORT_KNOWLEDGE_BASE"] = body.knowledge_base
    if body.extra_prompt is not None:
        changes["AI_SUPPORT_EXTRA_PROMPT"] = body.extra_prompt
    if not changes:
        raise HTTPException(400, "no changes")
    async with container.uow() as uow:
        try:
            written = await container.bot_config.set_values(uow, changes)
        except BotConfigError as exc:
            raise HTTPException(400, str(exc)) from exc
        await audit(uow, identity, "ai_support.patch", None, keys=written)
        await uow.commit()
    return {"ok": True, "applied": written}


class AiTestIn(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


@router.post("/test")
async def test_ai_support(
    body: AiTestIn,
    _: AdminIdentity = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, Any]:
    """Run one AI round-trip against a sample question (no real ticket, no tools fired
    against a real user — the synthetic user has no subscription)."""
    from src.core.enums import Locale
    from src.infrastructure.database.models.user import User

    probe = User(telegram_id=0, language=Locale.RU)
    reply, escalate, actions = await container.ai_support.generate_reply(
        probe, [("user", body.question)], readonly=True
    )
    return {"reply": reply, "escalate": escalate, "actions": actions}
