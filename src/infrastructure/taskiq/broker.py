"""taskiq broker + scheduler, plus a worker-lifetime AppContainer.

The webhook route enqueues work here and returns 200 immediately (gotcha #6). The worker
holds one :class:`AppContainer` so jobs share the same singletons (engine, panel client).
"""

from __future__ import annotations

from typing import Any

from taskiq import (
    SimpleRetryMiddleware,
    TaskiqEvents,
    TaskiqMessage,
    TaskiqMiddleware,
    TaskiqResult,
    TaskiqScheduler,
    TaskiqState,
)
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import ListQueueBroker

from src.core.config import get_settings
from src.core.logging import configure_logging
from src.infrastructure.di import AppContainer


class _TelemetryMiddleware(TaskiqMiddleware):
    """Report task crashes to the vendor telemetry (fire-and-forget, never raises).

    Reports only the FINAL failure: a task that SimpleRetryMiddleware will retry is
    skipped this attempt (mirrors its ``_retries + 1 < max_retries`` re-kick rule), so
    a retrying task isn't reported once per attempt.
    """

    def on_error(
        self, message: TaskiqMessage, result: TaskiqResult[Any], exception: BaseException
    ) -> None:
        if _container is None or not isinstance(exception, Exception):
            return
        retry_on = bool(message.labels.get("retry_on_error", False))
        retries = int(message.labels.get("_retries", 0) or 0)
        max_retries = int(message.labels.get("max_retries", 5) or 5)
        if retry_on and retries + 1 < max_retries:
            return  # a later attempt will report if the task ultimately fails
        _container.telemetry.report(exception, source="worker", context={"task": message.task_name})


_settings = get_settings()
# ListQueueBroker acks on pickup — without retries a task that raises is simply lost.
# Tasks opt in with `retry_on_error=True`; the payment reconciler covers longer outages.
broker = ListQueueBroker(_settings.redis.url).with_middlewares(
    SimpleRetryMiddleware(default_retry_count=5),
    _TelemetryMiddleware(),
)
scheduler = TaskiqScheduler(broker, sources=[LabelScheduleSource(broker)])

_container: AppContainer | None = None


def get_container() -> AppContainer:
    if _container is None:
        raise RuntimeError("AppContainer is not initialised (worker not started)")
    return _container


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def _on_startup(state: TaskiqState) -> None:
    global _container
    configure_logging(level=_settings.log.level, json=_settings.log.use_json)
    _container = AppContainer(_settings)


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def _on_shutdown(state: TaskiqState) -> None:
    if _container is not None:
        await _container.aclose()
