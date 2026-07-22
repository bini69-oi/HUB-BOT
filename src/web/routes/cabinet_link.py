"""Account linking («связка») — one person, many ways in.

Serves both audiences of ``/api/cabinet``: web-cabinet users (Bearer JWT) and
mini-app users (Telegram initData). Four flows:

* ``GET  /linked``               — what is attached to my account right now
* ``POST /link/email`` + confirm — attach an e-mail + password (code by mail),
                                   so a Telegram user can log in on the website
* ``POST /link/telegram``        — one-time deep-link code; opening the bot with it
                                   merges this web account into the Telegram one
* ``DELETE /link/oauth/{p}``     — detach a provider (guarded: never drop the last
                                   way into the account)
"""

from __future__ import annotations

import hashlib
import json
import re as _re
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError

from src.application.services.account_link import TG_LINK_PREFIX
from src.core.security import hash_password
from src.infrastructure.database.models.user import User
from src.infrastructure.di import AppContainer
from src.web.deps import get_container
from src.web.routes.cabinet import cabinet_user
from src.web.routes.cabinet_auth import _client_ip, _rate_limit

router = APIRouter(prefix="/api/cabinet", tags=["cabinet-link"])

_EMAIL_CODE_TTL = 15 * 60
_TG_CODE_TTL = 15 * 60
_MAX_CODE_ATTEMPTS = 5


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@router.get("/linked")
async def linked(
    user: User = Depends(cabinet_user), container: AppContainer = Depends(get_container)
) -> dict[str, Any]:
    from src.infrastructure.services.oauth import PROVIDER_NAMES

    async with container.uow() as uow:
        rows = await uow.linked_accounts.list_for_user(user.id)
        cfg = container.bot_config
        bot_username = str(await cfg.value(uow, "BOT_USERNAME") or "")
        available = []
        for name in PROVIDER_NAMES:
            cid = str(await cfg.value(uow, f"OAUTH_{name.upper()}_CLIENT_ID") or "")
            sec = str(await cfg.value(uow, f"OAUTH_{name.upper()}_CLIENT_SECRET") or "")
            if cid and sec:
                available.append(name)
    return {
        "email": user.email,
        "email_verified": user.email_verified,
        "has_password": bool(user.password_hash),
        "telegram": (
            {"id": user.telegram_id, "username": user.username}
            if user.telegram_id is not None
            else None
        ),
        "oauth": [
            {"provider": r.provider, "email": r.email, "display_name": r.display_name} for r in rows
        ],
        "available_providers": available,
        "bot_username": bot_username,
    }


class LinkEmailIn(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("invalid email")
        return v


@router.post("/link/email")
async def link_email(
    body: LinkEmailIn,
    request: Request,
    user: User = Depends(cabinet_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, Any]:
    """Attach an e-mail + password to the current (usually Telegram) account.

    Ownership of the address is proved by a 6-digit code sent to it; the password is
    kept hashed inside the pending-code payload and applied only on confirm.
    """
    await _rate_limit(container, "link_email", _client_ip(request), limit=10, window=3600)
    await _rate_limit(container, "link_email_uid", str(user.id), limit=5, window=3600)
    if user.email and user.email_verified:
        raise HTTPException(409, "почта уже привязана")
    async with container.uow() as uow:
        other = await uow.users.get_by_email(body.email)
        if other is not None and other.id != user.id:
            raise HTTPException(409, "эта почта уже занята другим аккаунтом")
    code = f"{secrets.randbelow(1_000_000):06d}"
    payload = {
        "email": body.email,
        "password_hash": hash_password(body.password),
        "code_hash": _hash(code),
        "attempts": 0,
    }
    await container.redis.set(f"link_email:{user.id}", json.dumps(payload), ex=_EMAIL_CODE_TTL)
    mailer = await container.build_mailer()
    sent = await mailer.send(
        body.email,
        "Код привязки почты",
        f"Код для привязки почты к аккаунту: {code}\n\nКод действует 15 минут.",  # noqa: RUF001
    )
    if not sent:
        raise HTTPException(503, "почта не настроена — обратитесь к владельцу сервиса")
    return {"ok": True, "email": body.email}


class LinkEmailConfirmIn(BaseModel):
    code: str = Field(..., min_length=4, max_length=16)


@router.post("/link/email/confirm")
async def link_email_confirm(
    body: LinkEmailConfirmIn,
    request: Request,
    user: User = Depends(cabinet_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, Any]:
    await _rate_limit(container, "link_email_confirm", _client_ip(request), limit=30, window=3600)
    key = f"link_email:{user.id}"
    raw = await container.redis.get(key)
    if raw is None:
        raise HTTPException(400, "код не запрошен или истёк")
    data = json.loads(raw)
    if data.get("attempts", 0) >= _MAX_CODE_ATTEMPTS:
        await container.redis.delete(key)
        raise HTTPException(429, "слишком много попыток — запроси новый код")
    if not secrets.compare_digest(_hash(body.code.strip()), str(data.get("code_hash") or "")):
        data["attempts"] = int(data.get("attempts", 0)) + 1
        await container.redis.set(key, json.dumps(data), ex=_EMAIL_CODE_TTL)
        raise HTTPException(400, "неверный код")
    async with container.uow() as uow:
        fresh = await uow.users.get(user.id)
        if fresh is None:
            raise HTTPException(401, "user gone")
        other = await uow.users.get_by_email(data["email"])
        if other is not None and other.id != fresh.id:
            raise HTTPException(409, "эта почта уже занята другим аккаунтом")
        fresh.email = data["email"]
        fresh.email_verified = True
        fresh.password_hash = data["password_hash"]
        try:
            await uow.commit()
        except IntegrityError as exc:  # lost the uq_users_email race
            raise HTTPException(409, "эта почта уже занята другим аккаунтом") from exc
    await container.redis.delete(key)
    return {"ok": True, "email": data["email"]}


@router.post("/link/telegram")
async def link_telegram(
    user: User = Depends(cabinet_user), container: AppContainer = Depends(get_container)
) -> dict[str, Any]:
    """One-time deep-link code: open the bot with it and the accounts merge."""
    if user.telegram_id is not None:
        raise HTTPException(409, "Telegram уже привязан")
    async with container.uow() as uow:
        bot_username = str(await container.bot_config.value(uow, "BOT_USERNAME") or "")
    if not bot_username:
        raise HTTPException(503, "бот не настроен")
    code = secrets.token_urlsafe(24)
    await container.redis.set(f"{TG_LINK_PREFIX}{code}", str(user.id), ex=_TG_CODE_TTL)
    return {
        "ok": True,
        "url": f"https://t.me/{bot_username}?start=link_{code}",
        "expires_in": _TG_CODE_TTL,
    }


@router.delete("/link/oauth/{provider}")
async def unlink_oauth(
    provider: str,
    user: User = Depends(cabinet_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, Any]:
    async with container.uow() as uow:
        rows = await uow.linked_accounts.list_for_user(user.id)
        mine = [r for r in rows if r.provider == provider]
        if not mine:
            raise HTTPException(404, "провайдер не привязан")
        # Never orphan the account: some way in must remain after the unlink.
        others_remain = len(rows) > len(mine)
        has_password_login = bool(user.email and user.email_verified and user.password_hash)
        has_telegram = user.telegram_id is not None
        if not (others_remain or has_password_login or has_telegram):
            raise HTTPException(409, "нельзя отвязать единственный способ входа")
        for r in mine:
            await uow.session.delete(r)
        await uow.commit()
    return {"ok": True, "unlinked": provider}
