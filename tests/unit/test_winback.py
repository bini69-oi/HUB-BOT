"""Win-back funnel (screen 08): step targeting, one-shot discount grant, Redis dedup.

Telegram delivery is stubbed at ``aiogram.Bot`` — the task resolves it at call time.
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from typing import TYPE_CHECKING, ClassVar, cast

import pytest

from src.application.services.bot_config import BotConfigService
from src.core.enums import SubscriptionStatus, UserStatus
from src.infrastructure.database.models.subscription import Subscription
from src.infrastructure.database.models.winback_step import WinbackStep
from src.infrastructure.database.uow import UnitOfWork
from src.infrastructure.taskiq import tasks
from tests.factories import make_user

if TYPE_CHECKING:
    from src.infrastructure.di import AppContainer

# _msk_now() convention: UTC-now shifted +3h (MSK wall clock, tzinfo stays UTC).
NOW_MSK = dt.datetime(2026, 7, 7, 12, 2, tzinfo=dt.UTC)


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool:
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True


class _FakeBot:
    sent: ClassVar[list[tuple[int, str]]] = []

    def __init__(self, token: str) -> None:
        self.session = SimpleNamespace()
        self.session.close = self._close

    async def _close(self) -> None: ...

    async def send_message(self, chat_id: int, text: str, reply_markup: object = None) -> None:
        _FakeBot.sent.append((chat_id, text))


def _container(uow: UnitOfWork) -> AppContainer:
    return cast(
        "AppContainer",
        SimpleNamespace(
            uow=lambda: uow,
            bot_config=BotConfigService(None),
            redis=_FakeRedis(),
            settings=SimpleNamespace(bot=SimpleNamespace(token="42:TEST")),
        ),
    )


@pytest.fixture
def winback_env(uow: UnitOfWork, monkeypatch: pytest.MonkeyPatch) -> AppContainer:
    container = _container(uow)
    monkeypatch.setattr(tasks, "get_container", lambda: container)
    monkeypatch.setattr(tasks, "_msk_now", lambda: NOW_MSK)
    monkeypatch.setattr("aiogram.Bot", _FakeBot)
    _FakeBot.sent = []
    return container


async def _expired_user(
    uow: UnitOfWork,
    *,
    telegram_id: int,
    days_ago: int,
    status: SubscriptionStatus = SubscriptionStatus.EXPIRED,
    user_status: UserStatus = UserStatus.ACTIVE,
) -> int:
    """User whose current subscription expired `days_ago` MSK-days before NOW_MSK."""
    user = await make_user(uow, telegram_id=telegram_id, status=user_status)
    expire_at = (NOW_MSK - dt.timedelta(days=days_ago)).replace(hour=15, minute=0) - dt.timedelta(
        hours=3
    )
    sub = await uow.subscriptions.add(
        Subscription(
            user_id=user.id,
            short_id=f"wb{telegram_id}",
            status=status,
            expire_at=expire_at,
        )
    )
    user.current_subscription_id = sub.id
    await uow.flush()
    return user.id


async def test_winback_targets_grant_and_dedup(uow: UnitOfWork, winback_env: AppContainer) -> None:
    async with uow:
        await uow.winback_steps.add(
            WinbackStep(offset_days=3, text="Скидка {discount}%", discount_pct=15)
        )
        hit_id = await _expired_user(uow, telegram_id=100, days_ago=3)
        await _expired_user(uow, telegram_id=200, days_ago=5)  # wrong day
        await _expired_user(uow, telegram_id=300, days_ago=3, status=SubscriptionStatus.ACTIVE)
        await _expired_user(uow, telegram_id=400, days_ago=3, user_status=UserStatus.BLOCKED)
        await uow.commit()

    assert await tasks.send_winback_offers() == 1
    assert _FakeBot.sent == [(100, "Скидка 15%")]

    async with uow:
        user = await uow.users.get(hit_id)
        assert user is not None and user.purchase_discount_pct == 15

    # Same day, next 5-min tick: Redis SETNX suppresses the duplicate.
    assert await tasks.send_winback_offers() == 0
    assert len(_FakeBot.sent) == 1


async def test_winback_discount_never_lowered(uow: UnitOfWork, winback_env: AppContainer) -> None:
    async with uow:
        await uow.winback_steps.add(WinbackStep(offset_days=1, text="wb", discount_pct=10))
        uid = await _expired_user(uow, telegram_id=100, days_ago=1)
        user = await uow.users.get(uid)
        assert user is not None
        user.purchase_discount_pct = 30  # bigger one-shot promo already granted
        await uow.commit()

    assert await tasks.send_winback_offers() == 1
    async with uow:
        user = await uow.users.get(uid)
        assert user is not None and user.purchase_discount_pct == 30


async def test_winback_disabled_or_off_window_is_silent(
    uow: UnitOfWork, winback_env: AppContainer
) -> None:
    async with uow:
        await uow.winback_steps.add(
            WinbackStep(offset_days=3, text="wb", discount_pct=5, enabled=False)
        )
        await uow.winback_steps.add(
            WinbackStep(offset_days=7, text="wb", discount_pct=5, send_time="09:00")
        )
        await _expired_user(uow, telegram_id=100, days_ago=3)
        await _expired_user(uow, telegram_id=200, days_ago=7)
        await uow.commit()

    assert await tasks.send_winback_offers() == 0
    assert _FakeBot.sent == []
