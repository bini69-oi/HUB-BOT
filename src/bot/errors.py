"""Global aiogram error handler: report to telemetry, answer the user gently.

Without it an exception in any handler is only logged and the user stares at a
silent bot. Now every crash produces a short error id — the user sees it and can
quote it to support; the same id arrives at the vendor ingest with the traceback.
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, Any

from aiogram.types.error_event import ErrorEvent

from src.core.logging import get_logger

if TYPE_CHECKING:
    from aiogram import Dispatcher

    from src.infrastructure.di import AppContainer

log = get_logger(__name__)

_USER_TEXT = "⚠️ Что-то пошло не так. Попробуйте ещё раз.\nКод ошибки: {error_id}"


def setup_error_handler(dp: Dispatcher, container: AppContainer) -> None:
    @dp.errors()
    async def _on_error(event: ErrorEvent) -> bool:
        update = event.update
        context: dict[str, Any] = {}
        message = getattr(update, "message", None)
        callback = getattr(update, "callback_query", None)
        if callback is not None and callback.data:
            context["callback_data"] = str(callback.data)[:64]
        if message is not None and message.text and message.text.startswith("/"):
            context["command"] = message.text.split()[0][:32]

        error_id = container.telemetry.report(event.exception, source="bot", context=context)
        log.error("unhandled bot error", error_id=error_id, exc_info=event.exception)

        text = _USER_TEXT.format(error_id=error_id)
        with suppress(Exception):  # notifying the user must not raise a second time
            if callback is not None:
                await callback.answer(text, show_alert=True)
            elif message is not None:
                await message.answer(text)
        return True  # handled — aiogram must not re-log or crash the polling loop
