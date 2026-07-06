"""Channel-subscription gate: require joining a channel before key actions (#1).

Config: ``CHANNEL_SUB_REQUIRED`` (bool) + ``CHANNEL_SUB_ID`` (channel @username or -100… id).
If the bot cannot read the channel (not an admin there / bad id), the gate fails OPEN — we log
and allow, so a misconfiguration never locks users out of buying.
"""

from __future__ import annotations

from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.core.logging import get_logger
from src.infrastructure.di import AppContainer

log = get_logger(__name__)

_OK_STATUSES = {"creator", "administrator", "member"}


def _channel_url(channel: str) -> str:
    if channel.startswith("http"):
        return channel
    return f"https://t.me/{channel.lstrip('@')}"


async def ensure_channel(event: Message | CallbackQuery, container: AppContainer) -> bool:
    """True if the user may proceed; otherwise show the join screen and return False."""
    async with container.uow() as uow:
        required = bool(await container.bot_config.value(uow, "CHANNEL_SUB_REQUIRED"))
        channel = str(await container.bot_config.value(uow, "CHANNEL_SUB_ID") or "").strip()
    if not required or not channel or event.from_user is None or event.bot is None:
        return True

    try:
        member = await event.bot.get_chat_member(channel, event.from_user.id)
    except Exception:
        log.warning("channel_gate_check_failed", channel=channel, exc_info=True)
        return True

    subscribed = member.status in _OK_STATUSES or (
        member.status == "restricted" and getattr(member, "is_member", False)
    )
    if subscribed:
        return True

    text = "Чтобы продолжить, подпишись на наш канал 👇"
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Открыть канал", url=_channel_url(channel))],
            [InlineKeyboardButton(text="✅ Я подписался", callback_data="check:sub")],
            [InlineKeyboardButton(text="‹ Меню", callback_data="nav:root")],
        ]
    )
    if isinstance(event, CallbackQuery):
        if event.message is not None:
            try:
                await event.message.edit_text(text, reply_markup=markup)  # type: ignore[union-attr]
            except Exception:
                await event.message.answer(text, reply_markup=markup)
        await event.answer()
    else:
        await event.answer(text, reply_markup=markup)
    return False
