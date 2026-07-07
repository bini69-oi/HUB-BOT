"""DeviceGuard: IP aggregation across nodes, limit matching, actions."""

from __future__ import annotations

from src.application.dto.pricing import PurchaseRequest
from src.application.services.device_guard import DeviceGuardService, GuardConfig
from src.application.services.remnawave import RemnawaveService
from src.application.services.subscription import SubscriptionService
from src.core.enums import Currency, PurchaseType, SubscriptionStatus
from src.infrastructure.database.uow import UnitOfWork
from tests.factories import make_plan, make_user
from tests.fakes import FakeRemnawaveClient


async def _grant(uow: UnitOfWork, device_limit: int | None = 3) -> tuple:
    fake = FakeRemnawaveClient()
    subs = SubscriptionService(RemnawaveService(fake))
    user = await make_user(uow)
    plan, _ = await make_plan(uow, device_limit=device_limit)
    await uow.commit()
    req = PurchaseRequest(
        user_id=user.id,
        plan_id=plan.id,
        duration_days=30,
        currency=Currency.RUB,
        purchase_type=PurchaseType.NEW,
    )
    sub = await subs.grant(uow, user=user, plan=plan, req=req)
    await uow.commit()
    return fake, sub


async def test_collect_ips_merges_nodes(uow: UnitOfWork) -> None:
    fake = FakeRemnawaveClient()
    guard = DeviceGuardService(fake)
    fake.users_ips["job-n1"] = [("sub_abc", ["1.1.1.1", "2.2.2.2"])]
    fake.users_ips["job-n2"] = [("sub_abc", ["2.2.2.2", "3.3.3.3"]), ("sub_zzz", ["9.9.9.9"])]
    usage = await guard.collect_ips(["n1", "n2"])
    assert usage["sub_abc"] == {"1.1.1.1", "2.2.2.2", "3.3.3.3"}
    assert usage["sub_zzz"] == {"9.9.9.9"}


async def test_scan_flags_over_limit_and_respects_tolerance(uow: UnitOfWork) -> None:
    async with uow:
        fake, sub = await _grant(uow, device_limit=2)
        guard = DeviceGuardService(fake)
        username = RemnawaveService.username_for(sub.short_id)

        # 3 IPs with limit 2 + tolerance 1 -> within tolerance, no violation
        usage = {username: {"1.1.1.1", "2.2.2.2", "3.3.3.3"}}
        assert await guard.scan(uow, usage, GuardConfig(tolerance=1)) == []

        # 4 IPs -> violation; default action is a pure alert (nothing disabled)
        usage = {username: {"1.1.1.1", "2.2.2.2", "3.3.3.3", "4.4.4.4"}}
        violations = await guard.scan(uow, usage, GuardConfig(tolerance=1))
        assert len(violations) == 1
        v = violations[0]
        assert v.subscription_id == sub.id
        assert v.limit == 2 and len(v.ips) == 4
        assert v.action == "alert"
        assert sub.status is SubscriptionStatus.ACTIVE


async def test_scan_matches_by_uuid_and_disable_action(uow: UnitOfWork) -> None:
    async with uow:
        fake, sub = await _grant(uow, device_limit=1)
        guard = DeviceGuardService(fake)
        usage = {str(sub.remnawave_uuid): {"1.1.1.1", "2.2.2.2", "3.3.3.3"}}
        violations = await guard.scan(uow, usage, GuardConfig(tolerance=0, action="disable"))
        assert len(violations) == 1
        assert violations[0].action == "disable"
        assert sub.status is SubscriptionStatus.DISABLED


async def test_scan_skips_unlimited_without_fallback(uow: UnitOfWork) -> None:
    async with uow:
        fake, sub = await _grant(uow, device_limit=None)
        guard = DeviceGuardService(fake)
        username = RemnawaveService.username_for(sub.short_id)
        usage = {username: {f"1.1.1.{i}" for i in range(20)}}
        # no device limit and max_ips=0 -> not checked
        assert await guard.scan(uow, usage, GuardConfig(max_ips=0)) == []
        # fallback limit applies when configured
        violations = await guard.scan(uow, usage, GuardConfig(max_ips=5, tolerance=0))
        assert len(violations) == 1
