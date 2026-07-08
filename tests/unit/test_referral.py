"""ReferralService: binding + at-most-once commission (gotcha #13)."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from src.application.services.referral import DEFAULT_COMMISSION_PERCENT, ReferralService
from src.infrastructure.database.models.referral import Referral, ReferralEarning
from src.infrastructure.database.uow import UnitOfWork
from tests.factories import make_user
from tests.fakes import RecordingEventBus


def _signup_bonus(user_id: int, referral_id: int) -> ReferralEarning:
    return ReferralEarning(
        user_id=user_id,
        referral_id=referral_id,
        amount_minor=0,
        reason="signup_days_bonus",
        is_issued=True,
    )


async def test_bind_sets_referrer_once(uow: UnitOfWork) -> None:
    svc = ReferralService(RecordingEventBus())
    async with uow:
        referrer = await make_user(uow, telegram_id=1)
        invited = await make_user(uow, telegram_id=2)
        await uow.commit()
        first = await svc.bind(uow, invited, referrer.referral_code)
        assert first is not None
        # a second bind attempt is ignored (one referrer per user)
        second = await svc.bind(uow, invited, referrer.referral_code)
        assert second is None
        assert invited.referred_by_id == referrer.id


async def test_commission_paid_once_per_transaction(uow: UnitOfWork) -> None:
    svc = ReferralService(RecordingEventBus())
    async with uow:
        referrer = await make_user(uow, telegram_id=1)
        invited = await make_user(uow, telegram_id=2)
        await uow.commit()
        await svc.bind(uow, invited, referrer.referral_code)
        await uow.commit()

        earning = await svc.reward_on_topup(
            uow, payer=invited, amount_minor=10000, transaction_id=42
        )
        assert earning is not None
        assert earning.amount_minor == 10000 * DEFAULT_COMMISSION_PERCENT // 100
        await uow.commit()

        referrer_id = referrer.id
        # Retried webhook with the same source transaction must not double-pay.
        again = await svc.reward_on_topup(uow, payer=invited, amount_minor=10000, transaction_id=42)
        await uow.commit()

    async with uow:
        refreshed = await uow.users.get(referrer_id)
        assert refreshed is not None
        assert refreshed.balance_minor == 2500  # credited exactly once
        assert again is earning or again.id == earning.id


async def test_signup_bonus_at_most_once_per_referral(uow: UnitOfWork) -> None:
    # The DB enforces one signup-days bonus per referral, so two concurrent workers can't both
    # grant it (#9) — an app-level check-then-insert alone could not.
    async with uow:
        r = await make_user(uow, telegram_id=1)
        i = await make_user(uow, telegram_id=2)
        await uow.commit()
        ref = Referral(referrer_id=r.id, referred_id=i.id)
        uow.session.add(ref)
        await uow.session.flush()
        rid, uid = ref.id, r.id
        uow.session.add(_signup_bonus(uid, rid))
        await uow.commit()

    with pytest.raises(IntegrityError):
        async with uow:
            uow.session.add(_signup_bonus(uid, rid))
            await uow.commit()
