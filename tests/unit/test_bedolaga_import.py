"""bedolaga importer: synthetic Postgres rows -> our schema, idempotently.

The read layer (asyncpg) is exercised against a live DB in migration; here we feed
``run()`` a synthetic ``data`` dict (the shape ``read_source`` returns) to cover the
transform/write logic without a Postgres.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from src.application.services.bedolaga_import import BedolagaImportService
from src.application.services.referral import ReferralService
from src.core.enums import RewardType, SubscriptionStatus, UserStatus
from src.infrastructure.database.uow import UnitOfWork
from tests.fakes import RecordingEventBus

FUTURE = dt.datetime(2099, 12, 31, tzinfo=dt.UTC)
PAST = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)


def _source() -> dict[str, list[dict[str, Any]]]:
    return {
        "users": [
            {
                "id": 1,
                "telegram_id": 111,
                "username": "alice",
                "status": "active",
                "language": "ru",
                "balance_kopeks": 15000,
                "has_had_paid_subscription": True,
                "referred_by_id": None,
                "referral_code": "ALICE1",
                "created_at": PAST,
            },
            {
                "id": 2,
                "telegram_id": 222,
                "username": "bob",
                "status": "active",
                "language": "en",
                "balance_kopeks": 0,
                "has_had_paid_subscription": True,
                "referred_by_id": 1,
                "referral_code": "BOB222",
                "created_at": PAST,
                "email": "Bob@Example.com",
                "email_verified": True,
                "password_hash": "scrypt$x",
            },
            {
                "id": 3,
                "telegram_id": 333,
                "username": "carol",
                "status": "blocked",
                "language": "ru",
                "balance_kopeks": 500,
                "has_had_paid_subscription": False,
                "referred_by_id": 1,
                "referral_code": "CAROL3",
                "created_at": PAST,
            },
        ],
        "subscriptions": [
            {
                "id": 1,
                "user_id": 1,
                "status": "active",
                "is_trial": False,
                "start_date": PAST,
                "end_date": FUTURE,
                "traffic_limit_gb": 100,
                "traffic_used_gb": 12.5,
                "subscription_url": "https://s/aa",
                "device_limit": 3,
                "connected_squads": ["sq-1"],
                "autopay_enabled": True,
                "remnawave_uuid": "11111111-1111-4111-8111-111111111111",
                "remnawave_short_uuid": "aa11bb22",
                "tariff_id": 5,
            },
            {
                "id": 2,
                "user_id": 2,
                "status": "active",
                "is_trial": True,
                "start_date": PAST,
                "end_date": PAST,
                "traffic_limit_gb": 0,
                "traffic_used_gb": 0,
                "subscription_url": "https://s/bb",
                "device_limit": 1,
                "connected_squads": None,
                "autopay_enabled": False,
                "remnawave_uuid": "22222222-2222-4222-8222-222222222222",
                "remnawave_short_uuid": "bb22cc33",
                "tariff_id": None,
            },
        ],
        "transactions": [
            {
                "id": 1,
                "user_id": 1,
                "type": "subscription_payment",
                "amount_kopeks": 19900,
                "payment_method": "yookassa",
                "external_id": "yk-1",
                "is_completed": True,
                "created_at": PAST,
                "completed_at": PAST,
            },
            {
                "id": 2,
                "user_id": 1,
                "type": "deposit",
                "amount_kopeks": 50000,
                "payment_method": "cryptobot",
                "external_id": "cb-2",
                "is_completed": True,
                "created_at": PAST,
                "completed_at": PAST,
            },
            {
                "id": 3,
                "user_id": 2,
                "type": "subscription_payment",
                "amount_kopeks": 0,
                "payment_method": "telegram_stars",
                "external_id": "tg-3",
                "is_completed": False,
                "created_at": PAST,
                "completed_at": None,
            },
        ],
        "promocodes": [
            {
                "id": 1,
                "code": "welcome",
                "type": "balance",
                "balance_bonus_kopeks": 10000,
                "subscription_days": 0,
                "max_uses": 100,
                "valid_until": FUTURE,
                "is_active": True,
            },
            {
                "id": 2,
                "code": "freedays",
                "type": "subscription_days",
                "balance_bonus_kopeks": 0,
                "subscription_days": 7,
                "max_uses": 50,
                "valid_until": None,
                "is_active": True,
            },
            {
                "id": 3,
                "code": "empty",
                "type": "none",
                "balance_bonus_kopeks": 0,
                "subscription_days": 0,
                "max_uses": 1,
                "valid_until": None,
                "is_active": False,
            },
        ],
    }


async def test_import_maps_and_is_idempotent(uow: UnitOfWork) -> None:
    svc = BedolagaImportService(ReferralService(RecordingEventBus()))
    async with uow:
        summary = await svc.run(uow, _source())
        await uow.commit()

    assert summary["users_created"] == 3
    assert summary["referrals_linked"] == 2  # bob + carol -> alice
    assert summary["subscriptions"] == 2
    assert summary["transactions"] == 2  # the incomplete stars txn is skipped
    assert summary["promocodes"] == 2  # the reward-less promo is skipped
    assert summary["skipped"]  # the empty promo left a note

    async with uow:
        alice = await uow.users.find_one(telegram_id=111)
        assert alice is not None and alice.balance_minor == 15000
        assert alice.has_had_paid_subscription is True
        assert alice.current_subscription_id is not None  # active sub linked

        bob = await uow.users.find_one(telegram_id=222)
        assert bob is not None and bob.email == "bob@example.com"  # web identity, lowercased
        assert bob.referred_by_id == alice.id  # referral linked

        carol = await uow.users.find_one(telegram_id=333)
        assert carol is not None and carol.status is UserStatus.BLOCKED

        sub = await uow.subscriptions.find_one(short_id="aa11bb22")
        assert sub is not None and sub.status is SubscriptionStatus.ACTIVE
        assert sub.traffic_limit_bytes == 100 * 1024**3
        assert alice.current_subscription_id == sub.id

        assert (await uow.transactions.find_one(external_id="yk-1")) is not None
        assert (await uow.transactions.find_one(external_id="cb-2")) is not None
        assert (await uow.transactions.find_one(external_id="tg-3")) is None  # incomplete skipped

        welcome = await uow.promocodes.find_one(code="WELCOME")
        assert welcome is not None and welcome.reward_type is RewardType.BALANCE
        free = await uow.promocodes.find_one(code="FREEDAYS")
        assert free is not None
        assert free.reward_type is RewardType.DURATION and free.reward_value == 7

    async with uow:
        again = await svc.run(uow, _source())
        await uow.commit()
    assert again["users_created"] == 0
    assert again["users_updated"] == 3
    assert again["transactions"] == 0
