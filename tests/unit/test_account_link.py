"""Merging a web-cabinet account into a Telegram account (account_link service)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.application.services.account_link import AccountLinkError, merge_web_into_telegram
from src.core.enums import (
    AuthType,
    Currency,
    RewardType,
    SubscriptionStatus,
    TransactionStatus,
    TransactionType,
)
from src.infrastructure.database.models.linked_account import LinkedAccount
from src.infrastructure.database.models.promocode import Promocode, PromocodeActivation
from src.infrastructure.database.models.referral import Referral
from src.infrastructure.database.models.subscription import Subscription
from src.infrastructure.database.models.transaction import Transaction
from src.infrastructure.database.models.user import User
from src.infrastructure.database.uow import UnitOfWork
from tests.factories import make_user


async def _make_web_user(uow: UnitOfWork, *, email: str = "web@example.com", **kw: object) -> User:
    from src.application.services.ids import generate_referral_code

    user = User(
        auth_type=AuthType.EMAIL,
        email=email,
        email_verified=True,
        password_hash="scrypt$x",
        referral_code=generate_referral_code(),
        currency=Currency.RUB,
        **kw,  # type: ignore[arg-type]
    )
    await uow.users.add(user)
    return user


async def test_merge_moves_everything(uow: UnitOfWork) -> None:
    async with uow:
        tg = await make_user(uow, telegram_id=111)
        web = await _make_web_user(uow, balance_minor=5000)
        tg.balance_minor = 1500
        sub = Subscription(
            user_id=web.id, short_id="WEB1", status=SubscriptionStatus.ACTIVE, plan_snapshot={}
        )
        uow.session.add(sub)
        uow.session.add(
            Transaction(
                user_id=web.id,
                type=TransactionType.DEPOSIT,
                status=TransactionStatus.COMPLETED,
                amount_minor=5000,
                currency=Currency.RUB,
            )
        )
        uow.session.add(
            LinkedAccount(user_id=web.id, provider="vk", external_id="42", display_name="Иван")
        )
        await uow.flush()
        web.current_subscription_id = sub.id
        await uow.commit()
        tg_id, web_id, sub_id = tg.id, web.id, sub.id

    async with uow:
        tg_user = await uow.users.get(tg_id)
        assert tg_user is not None
        merged = await merge_web_into_telegram(uow, tg_user, web_id)
        await uow.commit()

        assert merged.balance_minor == 6500
        assert merged.email == "web@example.com" and merged.email_verified
        assert merged.password_hash == "scrypt$x"
        assert merged.current_subscription_id == sub_id
        assert await uow.users.get(web_id) is None  # the web row is gone
        moved_sub = await uow.subscriptions.get(sub_id)
        assert moved_sub is not None and moved_sub.user_id == tg_id
        ident = await uow.linked_accounts.get_identity("vk", "42")
        assert ident is not None and ident.user_id == tg_id
        assert await uow.transactions.count(user_id=tg_id) == 1


async def test_merge_refuses_conflicts(uow: UnitOfWork) -> None:
    async with uow:
        tg = await make_user(uow, telegram_id=222, email="tg@example.com", email_verified=True)
        other_tg = await make_user(uow, telegram_id=333)
        web = await _make_web_user(uow, email="other@example.com")
        already_linked = await _make_web_user(uow, email="linked@example.com")
        already_linked.telegram_id = 444
        await uow.commit()
        tg_id, web_id, linked_id = tg.id, web.id, already_linked.id
        other_id = other_tg.id

    async with uow:
        tg_user = await uow.users.get(tg_id)
        assert tg_user is not None
        # different e-mails on both sides
        with pytest.raises(AccountLinkError):
            await merge_web_into_telegram(uow, tg_user, web_id)
        # the "web" account is in fact somebody's telegram account
        with pytest.raises(AccountLinkError):
            await merge_web_into_telegram(uow, tg_user, linked_id)
        # self-link
        with pytest.raises(AccountLinkError):
            await merge_web_into_telegram(uow, tg_user, tg_id)
        # stale code -> missing user
        with pytest.raises(AccountLinkError):
            await merge_web_into_telegram(uow, tg_user, 10_000)
    # sanity: nothing merged, all users still present
    async with uow:
        assert await uow.users.get(web_id) is not None
        assert await uow.users.get(other_id) is not None


async def test_merge_referral_and_promocode_dedup(uow: UnitOfWork) -> None:
    async with uow:
        referrer = await make_user(uow, telegram_id=555)
        tg = await make_user(uow, telegram_id=666)
        web = await _make_web_user(uow)
        web.referred_by_id = referrer.id
        uow.session.add(Referral(referrer_id=referrer.id, referred_id=web.id))
        promo = Promocode(code="WELCOME", reward_type=RewardType.BALANCE, reward_value=100)
        uow.session.add(promo)
        await uow.flush()
        # both accounts activated the same code — after the merge it must stay used ONCE
        uow.session.add(PromocodeActivation(promocode_id=promo.id, user_id=tg.id))
        uow.session.add(PromocodeActivation(promocode_id=promo.id, user_id=web.id))
        await uow.commit()
        referrer_id, tg_id, web_id, promo_id = referrer.id, tg.id, web.id, promo.id

    async with uow:
        tg_user = await uow.users.get(tg_id)
        assert tg_user is not None
        await merge_web_into_telegram(uow, tg_user, web_id)
        await uow.commit()

        # the referral binding moved to the survivor
        assert tg_user.referred_by_id == referrer_id
        binding = (
            await uow.session.scalars(select(Referral).where(Referral.referred_id == tg_id))
        ).first()
        assert binding is not None and binding.referrer_id == referrer_id
        activations = list(
            (
                await uow.session.scalars(
                    select(PromocodeActivation).where(PromocodeActivation.promocode_id == promo_id)
                )
            ).all()
        )
        assert len(activations) == 1 and activations[0].user_id == tg_id


async def test_merge_trial_spent_on_either_side(uow: UnitOfWork) -> None:
    async with uow:
        tg = await make_user(uow, telegram_id=777)
        web = await _make_web_user(uow)
        web.is_trial_available = False  # the web account already used its trial
        await uow.commit()
        tg_id, web_id = tg.id, web.id

    async with uow:
        tg_user = await uow.users.get(tg_id)
        assert tg_user is not None
        await merge_web_into_telegram(uow, tg_user, web_id)
        await uow.commit()
        assert tg_user.is_trial_available is False
