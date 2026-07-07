"""S2S postbacks: fire tracking pixels to an ad network on key events.

Traffic arbitrage needs a server-to-server ping when a user registers, takes the
trial or pays. We subscribe to the domain event bus and GET a URL template from
bot-config, expanding ``{user_id}``, ``{tg_id}``, ``{amount}``, ``{event}`` and
``{subid}`` (the user's campaign start_param). Best-effort — a dead tracker never
affects the bot.

Config keys: ``POSTBACK_ENABLED``, ``POSTBACK_URL_REGISTRATION``,
``POSTBACK_URL_TRIAL``, ``POSTBACK_URL_PURCHASE``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from src.application.common.events import DomainEvent
from src.application.events import SubscriptionPurchased, TrialGranted, UserRegistered
from src.core.logging import get_logger

if TYPE_CHECKING:
    from src.infrastructure.di import AppContainer

log = get_logger(__name__)


async def _subid(container: AppContainer, user_id: int) -> str:
    async with container.uow() as uow:
        user = await uow.users.get(user_id)
        if user is None or user.campaign_id is None:
            return ""
        campaign = await uow.campaigns.get(user.campaign_id)
        return str(campaign.start_param) if campaign else ""


async def _fire(container: AppContainer, key: str, **macros: str) -> None:
    async with container.uow() as uow:
        if not bool(await container.bot_config.value(uow, "POSTBACK_ENABLED")):
            return
        template = str(await container.bot_config.value(uow, key) or "").strip()
    if not template:
        return
    url = template
    for name, value in macros.items():
        url = url.replace("{" + name + "}", value)
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            await http.get(url)
    except httpx.HTTPError as exc:
        log.info("postback failed", key=key, error=str(exc))


def wire_postback_events(container: AppContainer) -> None:
    """Subscribe S2S postbacks to the event bus (registration / trial / purchase)."""

    async def _on_event(event: DomainEvent) -> None:
        if isinstance(event, UserRegistered):
            await _fire(
                container,
                "POSTBACK_URL_REGISTRATION",
                event="registration",
                user_id=str(event.user_id),
                tg_id=str(event.telegram_id or ""),
                amount="0",
                subid=await _subid(container, event.user_id),
            )
        elif isinstance(event, TrialGranted):
            await _fire(
                container,
                "POSTBACK_URL_TRIAL",
                event="trial",
                user_id=str(event.user_id),
                tg_id="",
                amount="0",
                subid=await _subid(container, event.user_id),
            )
        elif isinstance(event, SubscriptionPurchased):
            amount = "0"
            async with container.uow() as uow:
                txn = await uow.transactions.get(event.transaction_id)
                if txn is not None:
                    amount = f"{txn.amount_minor / 100:.2f}"
            await _fire(
                container,
                "POSTBACK_URL_PURCHASE",
                event="purchase",
                user_id=str(event.user_id),
                tg_id="",
                amount=amount,
                subid=await _subid(container, event.user_id),
            )

    container.event_bus.subscribe(_on_event)
