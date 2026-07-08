"""Admin: resellers / affiliates (screen «Партнёры»).

Onboard a partner with a deep-link code (``?start=partner_<code>``). Users who join through it
are attributed to the partner's own account, so the partner earns the standard referral
commission via the tested referral engine (see ``bot.handlers.start`` + ``ReferralService``).
The partner must have started the bot once (so their account has a referral code) and their
``telegram_id`` must be set here for attribution to pay out.
"""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.infrastructure.database.models.partner import Partner
from src.infrastructure.di import AppContainer
from src.web.deps import get_container
from src.web.routes.admin._common import audit, iso
from src.web.routes.admin.deps import AdminIdentity, require_admin

router = APIRouter(prefix="/partners")


def _serialize(p: Partner) -> dict[str, Any]:
    # Only real fields are exposed: the partner's earnings live in the referral ledger
    # (ReferralEarning), not on fabricated turnover/earnings columns (PART-1).
    return {
        "id": p.id,
        "name": p.name,
        "telegram_id": p.telegram_id,
        "code": p.code,
        "enabled": p.enabled,
        "created_at": iso(p.created_at),
    }


class PartnerIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    telegram_id: int | None = None
    code: str | None = Field(None, min_length=2, max_length=32)
    enabled: bool = True


class PartnerPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    telegram_id: int | None = None
    enabled: bool | None = None


@router.get("")
async def list_partners(container: AppContainer = Depends(get_container)) -> dict[str, Any]:
    async with container.uow() as uow:
        rows = await uow.partners.ordered()
    return {"items": [_serialize(p) for p in rows]}


@router.post("")
async def create_partner(
    body: PartnerIn,
    identity: AdminIdentity = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, Any]:
    code = (body.code or secrets.token_hex(4)).lower()
    async with container.uow() as uow:
        if await uow.partners.by_code(code) is not None:
            raise HTTPException(409, "code already in use")
        partner = Partner(
            name=body.name,
            telegram_id=body.telegram_id,
            code=code,
            enabled=body.enabled,
        )
        await uow.partners.add(partner)
        await audit(uow, identity, "partner.create", code)
        await uow.commit()
        return _serialize(partner)


@router.patch("/{partner_id}")
async def update_partner(
    partner_id: int,
    body: PartnerPatch,
    identity: AdminIdentity = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, Any]:
    async with container.uow() as uow:
        partner = await uow.partners.get(partner_id)
        if partner is None:
            raise HTTPException(404, "partner not found")
        for fld in ("name", "telegram_id", "enabled"):
            val = getattr(body, fld)
            if val is not None:
                setattr(partner, fld, val)
        await audit(uow, identity, "partner.update", str(partner_id))
        await uow.commit()
        return _serialize(partner)


@router.delete("/{partner_id}")
async def delete_partner(
    partner_id: int,
    identity: AdminIdentity = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, bool]:
    async with container.uow() as uow:
        if await uow.partners.get(partner_id) is None:
            raise HTTPException(404, "partner not found")
        await uow.partners.delete_by(id=partner_id)
        await audit(uow, identity, "partner.delete", str(partner_id))
        await uow.commit()
    return {"ok": True}
