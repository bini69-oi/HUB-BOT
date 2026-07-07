"""S2S postbacks fire tracker URLs with expanded macros on domain events."""

from __future__ import annotations

import httpx
import respx

from src.application.events import SubscriptionPurchased, UserRegistered
from src.core.enums import Currency, PurchaseType, TransactionStatus, TransactionType
from src.infrastructure.database.models.transaction import Transaction
from src.infrastructure.database.uow import UnitOfWork
from tests.factories import make_user


class _Bus:
    def __init__(self) -> None:
        self.handler = None

    def subscribe(self, fn) -> None:  # type: ignore[no-untyped-def]
        self.handler = fn

    async def publish(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.handler is not None:
            await self.handler(event)


class _Cfg:
    def __init__(self, values: dict[str, object]) -> None:
        self._values = values

    async def value(self, uow: object, key: str) -> object:
        return self._values.get(key, "")


class _Container:
    """Minimal stand-in exposing what postback wiring touches (fresh UoW each call)."""

    def __init__(self, session_factory, cfg: _Cfg) -> None:  # type: ignore[no-untyped-def]
        self.event_bus = _Bus()
        self.bot_config = cfg
        self._sf = session_factory

    def uow(self) -> UnitOfWork:
        return UnitOfWork(self._sf)


@respx.mock
async def test_postback_fires_registration_and_purchase(uow: UnitOfWork, session_factory) -> None:  # type: ignore[no-untyped-def]
    from src.infrastructure.services.postback import wire_postback_events

    reg = respx.get("https://track.example/reg").mock(return_value=httpx.Response(200))
    buy = respx.get("https://track.example/buy").mock(return_value=httpx.Response(200))

    async with uow:
        user = await make_user(uow)
        txn = Transaction(
            user_id=user.id,
            type=TransactionType.SUBSCRIPTION_PAYMENT,
            status=TransactionStatus.COMPLETED,
            amount_minor=19900,
            currency=Currency.RUB,
        )
        uow.session.add(txn)
        await uow.commit()

        cfg = _Cfg(
            {
                "POSTBACK_ENABLED": True,
                "POSTBACK_URL_REGISTRATION": "https://track.example/reg?u={user_id}&e={event}",
                "POSTBACK_URL_PURCHASE": "https://track.example/buy?u={user_id}&sum={amount}",
            }
        )
        container = _Container(session_factory, cfg)
        wire_postback_events(container)  # type: ignore[arg-type]

        await container.event_bus.publish(
            UserRegistered(user_id=user.id, telegram_id=user.telegram_id)
        )
        await container.event_bus.publish(
            SubscriptionPurchased(
                user_id=user.id,
                subscription_id=1,
                transaction_id=txn.id,
                purchase_type=PurchaseType.NEW,
            )
        )

    assert reg.called
    assert f"u={user.id}" in str(reg.calls.last.request.url)
    assert "e=registration" in str(reg.calls.last.request.url)
    assert buy.called
    assert "sum=199.00" in str(buy.calls.last.request.url)


@respx.mock
async def test_postback_skipped_when_disabled(uow: UnitOfWork, session_factory) -> None:  # type: ignore[no-untyped-def]
    from src.infrastructure.services.postback import wire_postback_events

    route = respx.get("https://track.example/reg").mock(return_value=httpx.Response(200))
    async with uow:
        user = await make_user(uow)
        await uow.commit()
        cfg = _Cfg(
            {"POSTBACK_ENABLED": False, "POSTBACK_URL_REGISTRATION": "https://track.example/reg"}
        )
        container = _Container(session_factory, cfg)
        wire_postback_events(container)  # type: ignore[arg-type]
        await container.event_bus.publish(UserRegistered(user_id=user.id))
    assert not route.called
