"""Background tasks. Import path registered with the worker (see compose.local.yml)."""

from __future__ import annotations

from uuid import UUID

from src.core.enums import TransactionStatus
from src.core.logging import get_logger
from src.infrastructure.taskiq.broker import broker, get_container

log = get_logger(__name__)


@broker.task
async def process_payment(payment_id: str, status: str) -> bool:
    """Complete a transaction from a verified webhook (idempotent CAS + fulfilment).

    Enqueued by the payment webhook route; never run inline. Safe to retry — a duplicate
    finds the transaction already terminal and no-ops.
    """
    container = get_container()
    async with container.uow() as uow:
        moved = await container.payments.process(
            uow,
            payment_id=UUID(payment_id),
            status=TransactionStatus(status),
        )
        await uow.commit()
    log.info("process_payment", payment_id=payment_id, status=status, advanced=moved)
    return moved


@broker.task
async def panel_write_retry(subscription_id: int) -> None:
    """Re-drive a failed panel write for a subscription (ADR-0005 retry queue).

    Placeholder for the reconcile/sync implementation — wire to RemnawaveService.apply once
    the sync mapper lands. Kept idempotent by design.
    """
    log.info("panel_write_retry", subscription_id=subscription_id)


@broker.task
async def run_backup() -> str | None:
    """Dump the Postgres DB to an encrypted zip in ./backups (pg_dump + pyzipper).

    Returns the archive path, or None when pg_dump is unavailable/failed. Sending the
    archive to the report group happens in the reports job, not here.
    """
    import asyncio
    import datetime as dt
    from pathlib import Path

    from src.infrastructure.services.backup import create_encrypted_zip, prune_old_backups

    container = get_container()
    db = container.settings.database
    backups = Path("backups")
    backups.mkdir(exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d_%H%M%S")
    dump_path = backups / f"db_{stamp}.sql"

    proc = await asyncio.create_subprocess_exec(
        "pg_dump",
        "--no-owner",
        "--format=plain",
        f"--file={dump_path}",
        f"--dbname=postgresql://{db.user}:{db.password}@{db.host}:{db.port}/{db.name}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        log.error("run_backup pg_dump failed", stderr=stderr.decode()[:400])
        dump_path.unlink(missing_ok=True)
        return None

    async with container.uow() as uow:
        password = str(await container.bot_config.value(uow, "BACKUP_ENCRYPTION_PASSWORD") or "")
        keep = int(await container.bot_config.value(uow, "BACKUP_KEEP_LAST"))
    out = backups / f"backup_{stamp}.zip"
    create_encrypted_zip([dump_path], out, password or container.settings.app.jwt_secret[:16])
    dump_path.unlink(missing_ok=True)
    prune_old_backups(backups, keep)
    log.info("run_backup done", path=str(out))
    return str(out)


@broker.task
async def send_broadcast(broadcast_id: int) -> None:
    """Deliver a broadcast to its audience, updating live progress counters.

    Uses a bare aiogram ``Bot`` (no dispatcher) so the worker doesn't need the bot
    process. Progress is committed in batches so the cabinet's polling sees it grow;
    per-user failures (blocked bot, deactivated account) increment ``failed``.
    """
    import asyncio
    import datetime as dt

    from aiogram import Bot
    from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.core.enums import BroadcastStatus
    from src.web.routes.admin.broadcasts import audience_stmt

    container = get_container()
    async with container.uow() as uow:
        b = await uow.broadcasts.get(broadcast_id)
        if b is None or b.status not in (BroadcastStatus.PENDING, BroadcastStatus.RUNNING):
            return
        b.status = BroadcastStatus.RUNNING
        b.started_at = dt.datetime.now(dt.UTC)
        chat_ids = [
            int(tg) for (tg,) in (await uow.session.execute(audience_stmt(b.audience))).all()
        ]
        text, button_enabled = b.text, b.button_enabled
        button_text, button_url = b.button_text, b.button_url
        await uow.commit()

    markup = None
    if button_enabled and button_text and button_url:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=button_text, url=button_url)]]
        )

    sent = failed = 0
    bot = Bot(token=container.settings.bot.token)
    try:
        for i, chat_id in enumerate(chat_ids, start=1):
            try:
                await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
                sent += 1
            except TelegramRetryAfter as exc:  # flood control — wait and retry once
                await asyncio.sleep(exc.retry_after)
                try:
                    await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
                    sent += 1
                except Exception:
                    failed += 1
            except TelegramForbiddenError:
                failed += 1
            except Exception:
                failed += 1
            # ~28 msg/s ceiling keeps us under Telegram's 30/s global limit.
            await asyncio.sleep(0.036)
            if i % 25 == 0 or i == len(chat_ids):
                async with container.uow() as uow:
                    b = await uow.broadcasts.get(broadcast_id)
                    if b is None or b.status is BroadcastStatus.CANCELED:
                        return
                    b.sent, b.failed = sent, failed
                    await uow.commit()
    finally:
        await bot.session.close()

    async with container.uow() as uow:
        b = await uow.broadcasts.get(broadcast_id)
        if b is not None:
            b.sent, b.failed = sent, failed
            b.status = BroadcastStatus.DONE
            b.finished_at = dt.datetime.now(dt.UTC)
            await uow.commit()
    log.info("send_broadcast done", broadcast_id=broadcast_id, sent=sent, failed=failed)
