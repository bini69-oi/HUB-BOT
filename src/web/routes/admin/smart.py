"""Admin: smart renewal reminder + RF holiday promo calendar (screen 08)."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from src.core.enums import HolidayRewardType
from src.infrastructure.database.models.holiday import Holiday
from src.infrastructure.di import AppContainer
from src.web.deps import get_container
from src.web.routes.admin._common import OkOut, audit
from src.web.routes.admin.deps import AdminIdentity, require_admin

router = APIRouter()

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_DAYS_RE = re.compile(r"^\d{1,2}(,\s*\d{1,2})*$")

# Seeded on first read: RF holiday calendar (admins toggle/edit afterwards).
_DEFAULT_HOLIDAYS: tuple[tuple[int, int, str], ...] = (
    (1, 1, "Новый год"),
    (1, 7, "Рождество"),
    (2, 23, "23 февраля"),
    (3, 8, "8 марта"),
    (5, 1, "1 мая"),
    (5, 9, "День Победы"),
    (6, 12, "День России"),
    (9, 1, "1 сентября"),
    (11, 4, "День народного единства"),
    (11, 27, "Чёрная пятница"),
    (12, 31, "Новогодняя ночь"),
)


@router.get("/smart-reminder")
async def get_reminder(container: AppContainer = Depends(get_container)) -> dict[str, Any]:
    async with container.uow() as uow:
        r = await uow.smart_reminder.get_or_create()
        await uow.commit()
    return {
        "enabled": r.enabled,
        "days_before": r.days_before,
        "send_time": r.send_time,
        "text": r.text,
        "button_enabled": r.button_enabled,
    }


class ReminderPatch(BaseModel):
    enabled: bool | None = None
    days_before: str | None = Field(None, max_length=32)
    send_time: str | None = Field(None, max_length=5)
    text: str | None = Field(None, min_length=1, max_length=4096)
    button_enabled: bool | None = None

    @field_validator("send_time")
    @classmethod
    def _time(cls, v: str | None) -> str | None:
        if v is not None and not _TIME_RE.match(v):
            raise ValueError("send_time must be HH:MM")
        return v

    @field_validator("days_before")
    @classmethod
    def _days(cls, v: str | None) -> str | None:
        if v is not None and not _DAYS_RE.match(v.strip()):
            raise ValueError('days_before must be a CSV of day numbers, e.g. "3,1"')
        return v


@router.patch("/smart-reminder")
async def patch_reminder(
    body: ReminderPatch,
    identity: AdminIdentity = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> OkOut:
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(400, "no changes")
    async with container.uow() as uow:
        r = await uow.smart_reminder.get_or_create()
        for k, v in data.items():
            setattr(r, k, v)
        await audit(uow, identity, "smart_reminder.patch", None, **data)
        await uow.commit()
    return OkOut()


def _holiday_row(h: Holiday) -> dict[str, Any]:
    return {
        "id": h.id,
        "date": f"{h.day:02d}.{h.month:02d}",
        "name": h.name,
        "enabled": h.enabled,
        "reward_type": h.reward_type.value,
        "value": h.value,
        "send_time": h.send_time,
        "results": h.results,
    }


@router.get("/holidays")
async def list_holidays(container: AppContainer = Depends(get_container)) -> dict[str, Any]:
    async with container.uow() as uow:
        rows = list(await uow.holidays.ordered())
        if not rows:
            for month, day, name in _DEFAULT_HOLIDAYS:
                await uow.holidays.add(Holiday(month=month, day=day, name=name))
            await uow.commit()
            rows = list(await uow.holidays.ordered())
    return {"items": [_holiday_row(h) for h in rows]}


class HolidayPatch(BaseModel):
    enabled: bool | None = None
    reward_type: HolidayRewardType | None = None
    value: int | None = Field(None, ge=0)
    send_time: str | None = Field(None, max_length=5)

    @field_validator("send_time")
    @classmethod
    def _time(cls, v: str | None) -> str | None:
        if v is not None and not _TIME_RE.match(v):
            raise ValueError("send_time must be HH:MM")
        return v


@router.patch("/holidays/{holiday_id}")
async def patch_holiday(
    holiday_id: int,
    body: HolidayPatch,
    identity: AdminIdentity = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> OkOut:
    data = body.model_dump(exclude_unset=True)
    async with container.uow() as uow:
        h = await uow.holidays.get(holiday_id)
        if h is None:
            raise HTTPException(404, "holiday not found")
        for k, v in data.items():
            setattr(h, k, v)
        await audit(
            uow,
            identity,
            "holiday.patch",
            f"holiday:{h.name}",
            **{k: (v.value if isinstance(v, HolidayRewardType) else v) for k, v in data.items()},
        )
        await uow.commit()
    return OkOut()
