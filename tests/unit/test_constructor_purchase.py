"""Constructor-mode purchases: pricing from period+pack, frozen overrides, renew.

SALES_MODE=constructor sells assembled subscriptions (period + traffic pack) booked under
the hidden service plan — the pack's limits must survive the snapshot round-trip exactly
like plan limits do (gotcha #5).
"""

from __future__ import annotations

import pytest

from src.application.services.payment import PaymentService
from src.application.services.pricing import PricingService
from src.application.services.purchase import CONSTRUCTOR_PLAN_CODE, PurchaseService
from src.application.services.referral import ReferralService
from src.application.services.remnawave import RemnawaveService
from src.application.services.subscription import SubscriptionService
from src.core.constants import BYTES_PER_GB
from src.core.enums import PurchaseType, TransactionStatus
from src.core.exceptions import PurchaseError
from src.infrastructure.database.models.constructor import ConstructorPeriod, TrafficPack
from src.infrastructure.database.uow import UnitOfWork
from tests.factories import make_user
from tests.fakes import FakeRemnawaveClient, RecordingEventBus


def _build() -> tuple[PurchaseService, PaymentService, FakeRemnawaveClient, RecordingEventBus]:
    fake = FakeRemnawaveClient()
    bus = RecordingEventBus()
    subs = SubscriptionService(RemnawaveService(fake))
    purchase = PurchaseService(PricingService(), subs, bus)
    payments = PaymentService(purchase, bus, ReferralService(bus))
    return purchase, payments, fake, bus


@pytest.fixture
def services() -> tuple[PurchaseService, PaymentService, FakeRemnawaveClient, RecordingEventBus]:
    return _build()


async def _seed(
    uow: UnitOfWork,
    *,
    days: int = 30,
    period_price: int = 10000,
    gb: int = 100,
    pack_price: int = 5000,
    active: bool = True,
) -> tuple[ConstructorPeriod, TrafficPack]:
    period = await uow.constructor_periods.add(
        ConstructorPeriod(days=days, price_minor=period_price, is_active=active)
    )
    pack = await uow.traffic_packs.add(TrafficPack(gb=gb, price_minor=pack_price, is_active=active))
    return period, pack


async def test_quote_sums_period_and_pack(uow: UnitOfWork, services) -> None:
    purchase, _payments, _fake, _bus = services
    async with uow:
        user = await make_user(uow)
        period, pack = await _seed(uow)
        req = await purchase.build_constructor_request(
            uow, user_id=user.id, period_id=period.id, pack_id=pack.id, device_limit=3
        )
        quote = await PricingService().quote(uow, req)

    assert req.duration_days == 30
    assert req.traffic_limit_bytes == 100 * BYTES_PER_GB
    assert quote.base.amount_minor == 15000
    assert quote.final.amount_minor == 15000
    assert quote.components == {"period": 10000, "pack": 5000}


async def test_inactive_rows_are_rejected(uow: UnitOfWork, services) -> None:
    purchase, _payments, _fake, _bus = services
    async with uow:
        user = await make_user(uow)
        period, pack = await _seed(uow)
        dead_pack = await uow.traffic_packs.add(
            TrafficPack(gb=500, price_minor=100, is_active=False)
        )
        dead_period = await uow.constructor_periods.add(
            ConstructorPeriod(days=60, price_minor=100, is_active=False)
        )
        with pytest.raises(PurchaseError):
            await purchase.build_constructor_request(
                uow, user_id=user.id, period_id=period.id, pack_id=dead_pack.id
            )
        with pytest.raises(PurchaseError):
            await purchase.build_constructor_request(
                uow, user_id=user.id, period_id=dead_period.id, pack_id=pack.id
            )


async def test_webhook_purchase_applies_pack_limits(uow: UnitOfWork, services) -> None:
    """Paid constructor purchase: the pack's traffic limit and the device limit survive the
    pricing snapshot and land on the panel user + local subscription (webhook fulfilment)."""
    purchase, payments, fake, _bus = services
    async with uow:
        user = await make_user(uow)
        period, pack = await _seed(uow)
        req = await purchase.build_constructor_request(
            uow, user_id=user.id, period_id=period.id, pack_id=pack.id, device_limit=3
        )
        txn, quote = await purchase.start(uow, req)
        await uow.commit()
        user_id, payment_id = user.id, txn.payment_id

    assert not quote.is_free
    assert txn.status is TransactionStatus.PENDING
    assert txn.amount_minor == 15000
    assert (txn.plan_snapshot or {})["traffic_limit_bytes"] == 100 * BYTES_PER_GB
    assert "100 ГБ" in (txn.plan_snapshot or {})["name"]

    async with uow:
        assert await payments.process(
            uow, payment_id=payment_id, status=TransactionStatus.COMPLETED
        )
        await uow.commit()

    panel_user = next(iter(fake.users.values()))
    assert panel_user.traffic_limit_bytes == 100 * BYTES_PER_GB
    assert panel_user.device_limit == 3
    async with uow:
        subs = await uow.subscriptions.active_for_user(user_id)
        assert len(subs) == 1
        assert subs[0].traffic_limit_bytes == 100 * BYTES_PER_GB
        assert subs[0].device_limit == 3
        plan = await uow.plans.get(subs[0].plan_id)
        assert plan is not None and plan.public_code == CONSTRUCTOR_PLAN_CODE
        assert not plan.is_active  # never in the buyable catalogue


async def test_renew_switches_traffic_pack(uow: UnitOfWork, services) -> None:
    purchase, payments, fake, _bus = services
    async with uow:
        user = await make_user(uow)
        period, pack = await _seed(uow)
        big_pack = await uow.traffic_packs.add(TrafficPack(gb=200, price_minor=9000))
        req = await purchase.build_constructor_request(
            uow, user_id=user.id, period_id=period.id, pack_id=pack.id, device_limit=3
        )
        txn, _ = await purchase.start(uow, req)
        await uow.commit()
        user_id = user.id
    async with uow:
        await payments.process(uow, payment_id=txn.payment_id, status=TransactionStatus.COMPLETED)
        await uow.commit()

    # Second purchase with a bigger pack renews the same subscription and upgrades the limit.
    async with uow:
        renew_req = await purchase.build_constructor_request(
            uow, user_id=user_id, period_id=period.id, pack_id=big_pack.id, device_limit=3
        )
        assert renew_req.purchase_type is PurchaseType.RENEW
        txn2, _ = await purchase.start(uow, renew_req)
        await uow.commit()
    async with uow:
        await payments.process(uow, payment_id=txn2.payment_id, status=TransactionStatus.COMPLETED)
        await uow.commit()

    async with uow:
        subs = await uow.subscriptions.active_for_user(user_id)
        assert len(subs) == 1  # renewed, not duplicated
        assert subs[0].traffic_limit_bytes == 200 * BYTES_PER_GB
    assert len(fake.users) == 1  # no second panel user
    panel_user = next(iter(fake.users.values()))
    assert panel_user.traffic_limit_bytes == 200 * BYTES_PER_GB
