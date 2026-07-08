"""Render the admin-built menu (or the built-in default when none is configured)."""

from __future__ import annotations

import contextlib

from aiogram.types import CallbackQuery, Message

from src.bot.banners import banner_for
from src.bot.keyboards import default_menu_markup, menu_keyboard, simple_keyboard, webapp_button
from src.bot.screen import show_media_screen
from src.infrastructure.database.models.user import User
from src.infrastructure.di import AppContainer


async def send_main_menu(
    target: Message | CallbackQuery, container: AppContainer, db_user: User
) -> None:
    async with container.uow() as uow:
        nodes = list(await uow.menu_nodes.tree())
        cfg = container.bot_config
        start_text = str(await cfg.value(uow, "START_MESSAGE"))
        miniapp_url = str(await cfg.value(uow, "SUBSCRIPTION_MINI_APP_URL") or "")
        welcome_sticker = str(await cfg.value(uow, "WELCOME_STICKER") or "")
        trial_enabled = bool(await cfg.value(uow, "TRIAL_ENABLED"))
        proxy_on = bool(await cfg.value(uow, "MTPROTO_PROXY_ENABLED")) and bool(
            await cfg.value(uow, "MTPROTO_PROXY_URL")
        )
        node_status_on = bool(await cfg.value(uow, "NODE_STATUS_ENABLED"))
        button_color = str(await cfg.value(uow, "BUTTON_COLOR_DEFAULT") or "") or None

    # Smart buttons appended to ANY menu — seeded, custom or fallback — so switching to a
    # constructor menu never loses them. Skipped when the tree already has that action.
    tree_actions = {n.payload for n in nodes if n.kind.value == "action"}
    has_miniapp_node = any(n.kind.value == "miniapp" for n in nodes)
    extras: list[tuple[str, str]] = []
    if trial_enabled and db_user.is_trial_available and "trial" not in tree_actions:
        extras.append(("🎁 Попробовать бесплатно", "act:trial:0"))
    if proxy_on and "proxy" not in tree_actions:
        extras.append(("🔌 MTProto-прокси", "act:proxy:0"))
    if node_status_on and "nodes" not in tree_actions:
        extras.append(("🌍 Статус серверов", "act:nodes:0"))
    if db_user.role.is_staff:
        extras.append(("🛠 Админка", "admin:menu"))

    if nodes:
        markup = menu_keyboard(
            nodes, None, miniapp_url=miniapp_url or None, default_color=button_color
        )
    else:
        markup = default_menu_markup(button_color)

    if extras:
        markup.inline_keyboard.extend(
            simple_keyboard(extras, columns=2, default_color=button_color).inline_keyboard
        )
    # Prominent mini-app CTA on top, unless the owner already placed a mini-app button.
    if miniapp_url.startswith("https://") and not has_miniapp_node:
        markup.inline_keyboard.insert(0, [webapp_button("📱 Открыть приложение", miniapp_url)])

    photo = await banner_for(container, "menu")
    if isinstance(target, CallbackQuery):
        # Smooth in-place swap (edit media/caption) when navigating back to the menu; falls
        # back to a fresh send + delete of the old card, so banners never pile up (NAV-1).
        await show_media_screen(target, photo, start_text, markup)
        await target.answer()
    else:
        # Fresh /start: optional decorative sticker, then the menu as a single banner message.
        if welcome_sticker:
            with contextlib.suppress(Exception):  # bad file_id must not break /start
                await target.answer_sticker(welcome_sticker)
        if photo is not None:
            with contextlib.suppress(Exception):
                await target.answer_photo(
                    photo,
                    caption=start_text,
                    reply_markup=markup,
                    parse_mode="HTML",
                )
                return
        with contextlib.suppress(Exception):  # HTML like every other render; plain on bad entities
            await target.answer(start_text, reply_markup=markup, parse_mode="HTML")
            return
        await target.answer(start_text, reply_markup=markup)
