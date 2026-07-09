"""Support tickets in the bot: create + converse (mirrors admin screen 11).

A user has at most one open/waiting ticket; new messages append to it. Replies from
the cabinet arrive via the admin API (which DMs the user); messages sent here while a
ticket is open are appended and flip the status back to OPEN.
"""

from __future__ import annotations

import contextlib
from html import escape as hesc

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.application.events import TicketOpened
from src.bot.banners import render_screen
from src.bot.keyboards import simple_keyboard
from src.bot.screen import ack
from src.core.enums import TicketAuthor, TicketStatus
from src.core.logging import get_logger
from src.infrastructure.database.base import utcnow
from src.infrastructure.database.models.ticket import Ticket, TicketMessage
from src.infrastructure.database.models.user import User
from src.infrastructure.di import AppContainer

router = Router(name="tickets")
log = get_logger(__name__)


class TicketForm(StatesGroup):
    waiting_text = State()


async def _maybe_ai_reply(
    message: Message, container: AppContainer, db_user: User, ticket_id: int
) -> bool:
    """If AI support is on and no human is in the loop, answer or escalate. Returns handled."""
    try:
        if not await container.ai_support.enabled():
            return False
        async with container.uow() as uow:
            msgs = await uow.ticket_messages.list(ticket_id=ticket_id)
        # A real operator already replied (an ADMIN message without the 🤖 marker) → AI steps back.
        if any(m.author is TicketAuthor.ADMIN and not m.text.startswith("🤖 ") for m in msgs):
            return False
        history = [(m.author.value, m.text) for m in msgs]
        with contextlib.suppress(Exception):
            await message.bot.send_chat_action(message.chat.id, "typing")  # type: ignore[union-attr]
        reply, escalate, _actions = await container.ai_support.generate_reply(db_user, history)
        if reply and not escalate:
            async with container.uow() as uow:
                await uow.ticket_messages.add(
                    TicketMessage(
                        ticket_id=ticket_id, author=TicketAuthor.ADMIN, text=("🤖 " + reply)[:4096]
                    )
                )
                t = await uow.tickets.get(ticket_id)
                if t is not None:
                    t.status = TicketStatus.WAITING
                await uow.commit()
            await message.answer(reply)
            return True
        # Escalation: tell the user a human is coming, alert the owner, leave the ticket OPEN.
        await message.answer(
            "Приняли обращение — подключаем оператора, ответим здесь в ближайшее время."
        )
        with contextlib.suppress(Exception):
            await container.notifier.notify_admins(
                f"⚠️ Тикет #{ticket_id} эскалирован ИИ — нужен оператор "
                f"(клиент {db_user.telegram_id}).",
                topic="alerts",
            )
        return True
    except Exception as exc:
        log.warning("ai support reply failed", ticket=ticket_id, error=str(exc))
        return False


async def begin_ticket(cb: CallbackQuery | Message, container: AppContainer, db_user: User) -> None:
    """Entry from the support action: show the open ticket or start a new one."""
    async with container.uow() as uow:
        open_tickets = await uow.tickets.list(user_id=db_user.id)
        active = next((t for t in open_tickets if t.status is not TicketStatus.CLOSED), None)
    if active is not None:
        text = (
            f"<b>🆘 Тикет #{active.id}</b>\n──────────\n"
            f"Тема: <b>{hesc(active.subject)}</b>\n"
            "Просто напиши сообщение — ответим в этой же переписке."
        )
    else:
        text = (
            "<b>🆘 Новый тикет</b>\n\n"
            "Опиши проблему одним сообщением — создадим тикет и ответим прямо здесь."
        )
    await render_screen(cb, container, "support", text, simple_keyboard([("‹ Меню", "nav:root")]))
    await ack(cb)


@router.message(Command("support"))
async def cmd_support(message: Message, container: AppContainer, db_user: User) -> None:
    await message.answer("Опиши проблему одним сообщением — создадим тикет и ответим здесь.")


@router.message(F.text & ~F.text.startswith("/"))
async def user_message(
    message: Message, container: AppContainer, db_user: User, state: FSMContext
) -> None:
    """Plain text outside flows: append to an open ticket, or open a new one."""
    if await state.get_state() is not None:
        return  # user is mid-FSM (e.g. entering a promocode) — don't hijack their input
    text = (message.text or "").strip()
    if not text:
        return
    async with container.uow() as uow:
        cfg = container.bot_config
        mode = str(await cfg.value(uow, "SUPPORT_MODE"))
        support_chat = str(await cfg.value(uow, "SUPPORT_CHAT_ID") or "")
        if mode == "redirect":
            return  # support goes to an external account; ignore free text
        tickets = await uow.tickets.list(user_id=db_user.id)
        active = next((t for t in tickets if t.status is not TicketStatus.CLOSED), None)
        created = False
        if active is None:
            active = Ticket(user_id=db_user.id, subject=text[:64])
            await uow.tickets.add(active)
            created = True
        await uow.ticket_messages.add(
            TicketMessage(ticket_id=active.id, author=TicketAuthor.USER, text=text[:4096])
        )
        active.status = TicketStatus.OPEN
        active.updated_at = utcnow()  # same-status assign is not dirty -> force the bump
        await uow.commit()
        ticket_id = active.id

    if created:
        # Instant "tickets" report topic (screen 14) listens on the bus.
        await container.event_bus.publish(
            TicketOpened(
                ticket_id=ticket_id,
                user_id=db_user.id,
                telegram_id=db_user.telegram_id,
                username=db_user.username,
                subject=text[:64],
            )
        )

    # AI support: if enabled and no human is handling this ticket yet, answer or escalate.
    if not await _maybe_ai_reply(message, container, db_user, ticket_id):
        if created:
            await message.answer(
                f"🆗 Тикет <b>#{ticket_id}</b> создан — ответим здесь.", parse_mode="HTML"
            )
        else:
            await message.answer("Добавил к тикету ✍️")

    # Mirror into the support group when configured.
    if support_chat.lstrip("-").isdigit():
        # Group misconfiguration must not break the user flow.
        with contextlib.suppress(Exception):
            await message.bot.send_message(  # type: ignore[union-attr]
                int(support_chat),
                f"🎫 #{ticket_id} от @{db_user.username or db_user.telegram_id}:\n\n{text[:1000]}",
            )
