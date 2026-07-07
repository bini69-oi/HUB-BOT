"""RemnawaveResyncService: heal panel drift, detect vanished panel users."""

from __future__ import annotations

import dataclasses
import datetime as dt

from src.application.dto.pricing import PurchaseRequest
from src.application.services.remnawave import RemnawaveService
from src.application.services.resync import RemnawaveResyncService
from src.application.services.subscription import SubscriptionService
from src.core.enums import Currency, SubscriptionStatus
from src.infrastructure.database.uow import UnitOfWork
from tests.factories import make_plan, make_user
from tests.fakes import FakeRemnawaveClient


async def _grant(uow: UnitOfWork):  # type: ignore[no-untyped-def]
    fake = FakeRemnawaveClient()
    subs = SubscriptionService(RemnawaveService(fake))
    user = await make_user(uow)
    plan, _ = await make_plan(uow)
    await uow.commit()
    req = PurchaseRequest(user_id=user.id, plan_id=plan.id, duration_days=30, currency=Currency.RUB)
    sub = await subs.grant(uow, user=user, plan=plan, req=req)
    await uow.commit()
    return fake, subs, sub


async def test_resync_heals_disabled_panel_user(uow: UnitOfWork) -> None:
    async with uow:
        fake, subs, sub = await _grant(uow)
        service = RemnawaveResyncService(fake, subs)
        assert sub.remnawave_uuid is not None

        # Someone disabled the user in the panel by hand.
        panel = fake.users[sub.remnawave_uuid]
        fake.users[sub.remnawave_uuid] = dataclasses.replace(panel, is_enabled=False)

        report = await service.resync(uow)
        assert report.checked == 1
        assert report.healed == 1
        # the panel user was re-enabled by re-applying our authoritative spec
        assert fake.users[sub.remnawave_uuid].is_enabled is True
        assert sub.status is SubscriptionStatus.ACTIVE


async def test_resync_disables_orphaned_local(uow: UnitOfWork) -> None:
    async with uow:
        fake, subs, sub = await _grant(uow)
        service = RemnawaveResyncService(fake, subs)
        assert sub.remnawave_uuid is not None
        del fake.users[sub.remnawave_uuid]  # deleted from the panel

        report = await service.resync(uow)
        assert report.orphaned_local == 1
        assert sub.status is SubscriptionStatus.DISABLED


async def test_resync_leaves_synced_alone(uow: UnitOfWork) -> None:
    async with uow:
        fake, subs, sub = await _grant(uow)
        service = RemnawaveResyncService(fake, subs)
        assert sub.remnawave_uuid is not None
        # align panel expiry exactly so there is no drift
        panel = fake.users[sub.remnawave_uuid]
        fake.users[sub.remnawave_uuid] = dataclasses.replace(panel, expire_at=sub.expire_at)

        report = await service.resync(uow)
        assert report.healed == 0 and report.orphaned_local == 0


async def test_resync_heals_expiry_drift(uow: UnitOfWork) -> None:
    async with uow:
        fake, subs, sub = await _grant(uow)
        service = RemnawaveResyncService(fake, subs)
        assert sub.remnawave_uuid is not None
        panel = fake.users[sub.remnawave_uuid]
        # panel says the sub ends 10 days earlier than what the customer paid for
        drifted = (sub.expire_at or dt.datetime.now(dt.UTC)) - dt.timedelta(days=10)
        fake.users[sub.remnawave_uuid] = dataclasses.replace(panel, expire_at=drifted)

        report = await service.resync(uow)
        assert report.healed == 1
        # re-applied our expiry back to the panel
        assert fake.users[sub.remnawave_uuid].expire_at == sub.expire_at
