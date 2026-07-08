"""Wire lifecycle domain events to owner-editable user DMs (notification templates).

Report topics (``reports.py``) go to the admin group; this module DMs the *user* the
owner-editable text for events that have no other natural send site — currently the
referral reward. Best-effort: a delivery failure never breaks the publishing flow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.common.events import DomainEvent
from src.application.events import ReferralRewardIssued
from src.core.enums import Currency
from src.core.logging import get_logger
from src.infrastructure.services.reports import fmt_amount

if TYPE_CHECKING:
    from src.infrastructure.di import AppContainer

log = get_logger(__name__)


def wire_user_notifications(container: AppContainer) -> None:
    """Subscribe user-facing lifecycle DMs to the domain event bus."""

    async def _on_event(event: DomainEvent) -> None:
        if isinstance(event, ReferralRewardIssued):
            await _referral_reward(container, event)

    container.event_bus.subscribe(_on_event)


async def _referral_reward(container: AppContainer, event: ReferralRewardIssued) -> None:
    from src.web.routes.admin.notifications import notification_text

    async with container.uow() as uow:
        referrer = await uow.users.get(event.referrer_id)
        if referrer is None or referrer.telegram_id is None:
            return
        currency = (referrer.currency or Currency.RUB).value
        text = await notification_text(
            uow,
            "referral_reward",
            name=referrer.first_name or "",
            amount=fmt_amount(event.amount_minor, currency),
        )
    if text:
        await container.notifier.notify_user(referrer.telegram_id, text)
