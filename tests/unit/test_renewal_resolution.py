"""resolve_purchase_type — never mint a duplicate panel account when one already exists.

Regression for the "оплатил → создался новый аккаунт, подписка не продлилась" bug on migrated
installs: imported subs carry plan_id NULL, so the old resolver (which required plan_id == /
is not None AND a *usable* status) returned NEW for every re-purchase, and grant() minted a
fresh Remnawave user — orphaning the migrated account. Hit all 273 Lazeyka users.
"""

from __future__ import annotations

import datetime as dt
import uuid as uuid_mod

from src.application.dto.pricing import PurchaseRequest
from src.application.services.ids import generate_short_id
from src.application.services.pricing import PricingService
from src.application.services.purchase import PurchaseService
from src.application.services.remnawave import RemnawaveService
from src.application.services.subscription import SubscriptionService
from src.core.enums import Currency, PurchaseType, SubscriptionStatus
from src.infrastructure.database.models.subscription import Subscription
from src.infrastructure.database.uow import UnitOfWork
from tests.factories import make_plan, make_user
from tests.fakes import FakeRemnawaveClient, RecordingEventBus


def _purchase() -> tuple[PurchaseService, FakeRemnawaveClient]:
    fake = FakeRemnawaveClient()
    subs = SubscriptionService(RemnawaveService(fake))
    return PurchaseService(PricingService(), subs, RecordingEventBus()), fake


async def _add_sub(
    uow: UnitOfWork,
    user,
    *,
    plan_id: int | None,
    status: SubscriptionStatus,
    remnawave_uuid: uuid_mod.UUID | None = "auto",  # type: ignore[assignment]
    short_id: str | None = None,
    expire_at: dt.datetime | None = None,
) -> Subscription:
    if remnawave_uuid == "auto":
        remnawave_uuid = uuid_mod.uuid4()
    sub = Subscription(
        user_id=user.id,
        remnawave_uuid=remnawave_uuid,
        short_id=short_id or generate_short_id(),
        plan_id=plan_id,
        status=status,
        expire_at=expire_at,
    )
    await uow.subscriptions.add(sub)
    user.current_subscription_id = sub.id
    await uow.flush()
    return sub


async def test_migrated_plan_less_sub_renews(uow: UnitOfWork) -> None:
    purchase, _ = _purchase()
    async with uow:
        user = await make_user(uow)
        plan, _ = await make_plan(uow, price_minor=30000)
        sub = await _add_sub(uow, user, plan_id=None, status=SubscriptionStatus.ACTIVE)
        await uow.commit()
        ptype, sub_id = await purchase.resolve_purchase_type(uow, user.id, plan.id)
    assert ptype is PurchaseType.RENEW
    assert sub_id == sub.id


async def test_expired_same_plan_revives_as_renew(uow: UnitOfWork) -> None:
    purchase, _ = _purchase()
    async with uow:
        user = await make_user(uow)
        plan, _ = await make_plan(uow, price_minor=30000)
        sub = await _add_sub(uow, user, plan_id=plan.id, status=SubscriptionStatus.EXPIRED)
        await uow.commit()
        ptype, sub_id = await purchase.resolve_purchase_type(uow, user.id, plan.id)
    assert ptype is PurchaseType.RENEW
    assert sub_id == sub.id


async def test_different_known_plan_is_change(uow: UnitOfWork) -> None:
    purchase, _ = _purchase()
    async with uow:
        user = await make_user(uow)
        plan_a, _ = await make_plan(uow, code="a", price_minor=30000)
        plan_b, _ = await make_plan(uow, code="b", price_minor=40000)
        sub = await _add_sub(uow, user, plan_id=plan_a.id, status=SubscriptionStatus.ACTIVE)
        await uow.commit()
        ptype, sub_id = await purchase.resolve_purchase_type(uow, user.id, plan_b.id)
    assert ptype is PurchaseType.CHANGE
    assert sub_id == sub.id


async def test_no_subscription_is_new(uow: UnitOfWork) -> None:
    purchase, _ = _purchase()
    async with uow:
        user = await make_user(uow)
        plan, _ = await make_plan(uow, price_minor=30000)
        await uow.commit()
        ptype, sub_id = await purchase.resolve_purchase_type(uow, user.id, plan.id)
    assert ptype is PurchaseType.NEW
    assert sub_id is None


async def test_deleted_sub_is_new(uow: UnitOfWork) -> None:
    purchase, _ = _purchase()
    async with uow:
        user = await make_user(uow)
        plan, _ = await make_plan(uow, price_minor=30000)
        await _add_sub(uow, user, plan_id=plan.id, status=SubscriptionStatus.DELETED)
        await uow.commit()
        ptype, _ = await purchase.resolve_purchase_type(uow, user.id, plan.id)
    assert ptype is PurchaseType.NEW  # panel account is gone -> mint a fresh one


async def test_uuidless_sub_is_new(uow: UnitOfWork) -> None:
    purchase, _ = _purchase()
    async with uow:
        user = await make_user(uow)
        plan, _ = await make_plan(uow, price_minor=30000)
        await _add_sub(
            uow, user, plan_id=plan.id, status=SubscriptionStatus.PENDING, remnawave_uuid=None
        )
        await uow.commit()
        ptype, _ = await purchase.resolve_purchase_type(uow, user.id, plan.id)
    assert ptype is PurchaseType.NEW  # never provisioned -> nothing to extend


async def test_migrated_renew_extends_same_account_and_adopts_plan(uow: UnitOfWork) -> None:
    """End-to-end: renewing a migrated (plan-less) sub extends the SAME Remnawave user, adopts
    the purchased plan, and does NOT provision a second account."""
    purchase, fake = _purchase()
    now = dt.datetime.now(dt.UTC)
    async with uow:
        user = await make_user(uow, telegram_id=4242)
        plan, _ = await make_plan(uow, price_minor=30000)
        # a migrated panel user already exists on the panel
        rw = RemnawaveService(fake)
        spec = rw.build_spec(
            short_id="mig00001",
            telegram_id=user.telegram_id,
            expire_at=now - dt.timedelta(days=2),  # already expired
            traffic_limit_bytes=0,
            device_limit=None,
            internal_squads=(),
            external_squad=None,
        )
        panel = await fake.create_user(spec)
        sub = await _add_sub(
            uow,
            user,
            plan_id=None,
            status=SubscriptionStatus.EXPIRED,
            remnawave_uuid=panel.uuid,
            short_id="mig00001",
            expire_at=now - dt.timedelta(days=2),
        )
        await uow.commit()

        assert len(fake.users) == 1
        ptype, sub_id = await purchase.resolve_purchase_type(uow, user.id, plan.id)
        assert ptype is PurchaseType.RENEW
        req = PurchaseRequest(
            user_id=user.id,
            plan_id=plan.id,
            duration_days=30,
            currency=Currency.RUB,
            purchase_type=PurchaseType.RENEW,
            subscription_id=sub_id,
        )
        renewed = await purchase._provision(uow, user=user, plan=plan, req=req)
        await uow.commit()

    assert renewed.id == sub.id  # same subscription row, not a new one
    assert renewed.remnawave_uuid == panel.uuid  # same panel account
    assert renewed.plan_id == plan.id  # adopted the purchased plan
    assert renewed.status is SubscriptionStatus.ACTIVE
    assert renewed.expire_at is not None and renewed.expire_at > now  # revived + extended
    assert len(fake.users) == 1  # ⭐ no duplicate account minted
