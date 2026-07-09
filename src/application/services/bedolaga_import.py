"""Importer: remnawave-bedolaga-telegram-bot (PostgreSQL) -> our schema.

Bedolaga keeps everything in Postgres. Unlike shopbot it already stores money as
integer **kopeks** and datetimes as timezone-aware UTC, and each subscription carries
its Remnawave uuid/short-uuid — which maps 1:1 onto our «panel-user per subscription»
invariant, so subscribers keep working mid-migration.

The source is a live Postgres, so the caller passes a read-only DSN
(``postgresql://user:pass@host:port/db``). Internal FKs use bedolaga's own row ids
(``subscriptions.user_id`` -> ``users.id``, ``users.referred_by_id`` -> ``users.id``),
so users are indexed by their bedolaga id for the second-pass links.

Idempotent: users match by telegram_id, subscriptions by remnawave_uuid, transactions
by external_id, promocodes by code — re-running updates instead of duplicating. Panel
users are NOT touched: we adopt the existing uuids.
"""

from __future__ import annotations

import datetime as dt
import uuid as uuid_mod
from typing import TYPE_CHECKING, Any

from src.application.services.ids import generate_referral_code, generate_short_id
from src.core.enums import (
    Currency,
    Locale,
    PaymentGatewayType,
    RewardType,
    SubscriptionStatus,
    TransactionStatus,
    TransactionType,
    UserStatus,
)
from src.infrastructure.database.models.promocode import Promocode
from src.infrastructure.database.models.subscription import Subscription
from src.infrastructure.database.models.transaction import Transaction
from src.infrastructure.database.models.user import User

if TYPE_CHECKING:
    from src.application.services.referral import ReferralService
    from src.infrastructure.database.uow import UnitOfWork

GIB = 1024**3

# bedolaga transaction.type -> ours (unknown -> DEPOSIT so money isn't lost)
_TXN_TYPE = {
    "deposit": TransactionType.DEPOSIT,
    "topup": TransactionType.DEPOSIT,
    "subscription_payment": TransactionType.SUBSCRIPTION_PAYMENT,
    "subscription": TransactionType.SUBSCRIPTION_PAYMENT,
    "purchase": TransactionType.SUBSCRIPTION_PAYMENT,
    "refund": TransactionType.REFUND,
    "referral_reward": TransactionType.REFERRAL_REWARD,
    "referral": TransactionType.REFERRAL_REWARD,
    "gift": TransactionType.GIFT,
    "admin_adjust": TransactionType.GIFT,
}
# bedolaga payment_method -> our gateway enum (best effort; None = unknown/manual)
_GATEWAY = {
    "yookassa": PaymentGatewayType.YOOKASSA,
    "cryptobot": PaymentGatewayType.CRYPTOBOT,
    "cryptomus": PaymentGatewayType.CRYPTOMUS,
    "heleket": PaymentGatewayType.HELEKET,
    "platega": PaymentGatewayType.PLATEGA,
    "wata": PaymentGatewayType.WATA,
    "freekassa": PaymentGatewayType.FREEKASSA,
    "mulenpay": PaymentGatewayType.MULENPAY,
    "telegram_stars": PaymentGatewayType.TELEGRAM_STARS,
    "stars": PaymentGatewayType.TELEGRAM_STARS,
}
_TABLES = ("users", "subscriptions", "transactions", "promocodes")


def _to_utc(raw: object) -> dt.datetime | None:
    """Bedolaga stores tz-aware UTC already — just normalize to aware UTC."""
    if raw is None:
        return None
    if isinstance(raw, dt.datetime):
        return raw.astimezone(dt.UTC) if raw.tzinfo else raw.replace(tzinfo=dt.UTC)
    return None


def _kopeks(raw: object) -> int:
    """Bedolaga already stores money as integer kopeks — take it as-is, defensively."""
    if isinstance(raw, bool) or raw is None:
        return 0
    if isinstance(raw, (int, float)):
        return int(raw)
    try:
        return int(str(raw))
    except (ValueError, TypeError):
        return 0


async def read_source(dsn: str) -> dict[str, list[dict[str, Any]]]:
    """Connect read-only to a bedolaga Postgres and pull the tables we migrate."""
    import asyncpg  # type: ignore[import-untyped]  # local: only for a migration, not hot path

    conn = await asyncpg.connect(dsn, timeout=20)
    try:
        out: dict[str, list[dict[str, Any]]] = {}
        for table in _TABLES:
            try:
                rows = await conn.fetch(f'SELECT * FROM "{table}"')
            except asyncpg.PostgresError:
                rows = []
            out[table] = [dict(r) for r in rows]
        return out
    finally:
        await conn.close()


async def probe(dsn: str) -> dict[str, Any]:
    """Cheap validation + row counts so the admin sees what will migrate."""
    try:
        data = await read_source(dsn)
    except Exception as exc:
        return {"ok": False, "detail": f"не удалось подключиться к БД bedolaga: {exc}"}
    if not data.get("users"):
        return {"ok": False, "detail": "таблица users пуста или это не БД bedolaga"}
    paid = [t for t in data["transactions"] if t.get("is_completed")]
    return {
        "ok": True,
        "counts": {
            "users": len(data["users"]),
            "subscriptions": len(data["subscriptions"]),
            "paid_transactions": len(paid),
            "promocodes": len(data["promocodes"]),
        },
    }


class BedolagaImportService:
    def __init__(self, referrals: ReferralService) -> None:
        self._referrals = referrals

    async def run(self, uow: UnitOfWork, data: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "users_created": 0,
            "users_updated": 0,
            "referrals_linked": 0,
            "subscriptions": 0,
            "transactions": 0,
            "promocodes": 0,
            "skipped": [],
        }
        by_bid = await self._import_users(uow, data["users"], summary)
        await self._link_referrals(uow, data["users"], by_bid, summary)
        await self._import_subscriptions(uow, data["subscriptions"], by_bid, summary)
        await self._import_transactions(uow, data["transactions"], by_bid, summary)
        await self._import_promocodes(uow, data["promocodes"], summary)
        return summary

    async def _import_users(
        self, uow: UnitOfWork, rows: list[dict[str, Any]], summary: dict[str, Any]
    ) -> dict[int, User]:
        by_bid: dict[int, User] = {}
        for row in rows:
            tid = row.get("telegram_id")
            if not tid:
                continue
            tid = int(tid)
            user = await uow.users.find_one(telegram_id=tid)
            if user is None:
                user = User(
                    telegram_id=tid,
                    username=(row.get("username") or None),
                    first_name=(row.get("first_name") or None),
                    last_name=(row.get("last_name") or None),
                    referral_code=str(row.get("referral_code") or "") or generate_referral_code(),
                    currency=Currency.RUB,
                    balance_minor=_kopeks(row.get("balance_kopeks")),
                    language=Locale.EN
                    if str(row.get("language") or "ru")[:2] == "en"
                    else Locale.RU,
                )
                await uow.users.add(user)
                created = _to_utc(row.get("created_at"))
                if created is not None:
                    user.created_at = created
                summary["users_created"] += 1
            else:
                user.balance_minor = _kopeks(row.get("balance_kopeks"))
                summary["users_updated"] += 1
            user.has_had_paid_subscription = bool(row.get("has_had_paid_subscription"))
            if str(row.get("status") or "").lower() in {"blocked", "banned", "deleted"}:
                user.status = UserStatus.BLOCKED
            # Web-cabinet identity travels too — bedolaga has email/OAuth accounts.
            if row.get("email"):
                user.email = str(row["email"]).lower()
                user.email_verified = bool(row.get("email_verified"))
                if row.get("password_hash"):
                    user.password_hash = str(row["password_hash"])
            by_bid[int(row["id"])] = user
        await uow.session.flush()
        return by_bid

    async def _link_referrals(
        self,
        uow: UnitOfWork,
        rows: list[dict[str, Any]],
        by_bid: dict[int, User],
        summary: dict[str, Any],
    ) -> None:
        """Second pass: bedolaga stores the referrer's internal row id."""
        for row in rows:
            ref = row.get("referred_by_id")
            referred = by_bid.get(int(row["id"]))
            if not ref or referred is None or referred.referred_by_id is not None:
                continue
            referrer = by_bid.get(int(ref))
            if referrer is None or referrer.id == referred.id:
                continue
            bound = await self._referrals.bind(uow, referred, referrer.referral_code)
            if bound is not None:
                summary["referrals_linked"] += 1

    async def _import_subscriptions(
        self,
        uow: UnitOfWork,
        rows: list[dict[str, Any]],
        by_bid: dict[int, User],
        summary: dict[str, Any],
    ) -> None:
        now = dt.datetime.now(dt.UTC)
        best_sub: dict[int, Subscription] = {}
        for row in rows:
            user = by_bid.get(int(row.get("user_id") or 0))
            raw_uuid = row.get("remnawave_uuid")
            if user is None or not raw_uuid:
                summary["skipped"].append(f"подписка #{row.get('id')}: нет юзера или uuid панели")
                continue
            try:
                panel_uuid = uuid_mod.UUID(str(raw_uuid))
            except ValueError:
                summary["skipped"].append(f"подписка #{row.get('id')}: кривой uuid панели")
                continue

            expire = _to_utc(row.get("end_date"))
            is_trial = bool(row.get("is_trial"))
            if expire is not None and expire > now:
                status = SubscriptionStatus.TRIAL if is_trial else SubscriptionStatus.ACTIVE
            else:
                status = SubscriptionStatus.EXPIRED

            sub = await uow.subscriptions.find_one(remnawave_uuid=panel_uuid)
            if sub is None:
                short = str(row.get("remnawave_short_uuid") or row.get("remnawave_short_id") or "")[
                    :16
                ]
                short = short or generate_short_id()
                if await uow.subscriptions.find_one(short_id=short) is not None:
                    short = generate_short_id()
                sub = Subscription(user_id=user.id, remnawave_uuid=panel_uuid, short_id=short)
                await uow.subscriptions.add(sub)
            sub.status = status
            sub.is_trial = is_trial
            sub.start_at = _to_utc(row.get("start_date")) or now
            sub.expire_at = expire
            sub.subscription_url = row.get("subscription_url") or None
            sub.crypto_link = row.get("subscription_crypto_link") or None
            sub.traffic_limit_bytes = int(row.get("traffic_limit_gb") or 0) * GIB
            sub.traffic_used_bytes = int(float(row.get("traffic_used_gb") or 0) * GIB)
            sub.device_limit = row.get("device_limit")
            sub.autopay_enabled = bool(row.get("autopay_enabled"))
            squads = row.get("connected_squads")
            if isinstance(squads, list) and squads:
                sub.internal_squads = [str(s) for s in squads]
            sub.plan_snapshot = {
                "name": "Imported",
                "source": "bedolaga",
                "tariff_id": row.get("tariff_id"),
            }
            summary["subscriptions"] += 1

            if status.is_usable:
                current = best_sub.get(user.id)
                if current is None or (sub.expire_at or now) > (current.expire_at or now):
                    best_sub[user.id] = sub

        await uow.session.flush()
        for user_id, sub in best_sub.items():
            user = await uow.users.get(user_id)
            if user is not None and user.current_subscription_id is None:
                user.current_subscription_id = sub.id

    async def _import_transactions(
        self,
        uow: UnitOfWork,
        rows: list[dict[str, Any]],
        by_bid: dict[int, User],
        summary: dict[str, Any],
    ) -> None:
        for row in rows:
            if not row.get("is_completed"):
                continue
            user = by_bid.get(int(row.get("user_id") or 0))
            if user is None:
                continue
            external = str(row.get("external_id") or "") or f"bedolaga-{row.get('id')}"
            if await uow.transactions.find_one(external_id=external) is not None:
                continue
            method = str(row.get("payment_method") or "")
            created = _to_utc(row.get("created_at")) or dt.datetime.now(dt.UTC)
            txn = Transaction(
                user_id=user.id,
                type=_TXN_TYPE.get(str(row.get("type") or "").lower(), TransactionType.DEPOSIT),
                status=TransactionStatus.COMPLETED,
                amount_minor=_kopeks(row.get("amount_kopeks")),
                currency=Currency.RUB,
                external_id=external,
                gateway_type=_GATEWAY.get(method.lower()),
                gateway_display_name=method or "bedolaga",
                completed_at=_to_utc(row.get("completed_at")) or created,
            )
            await uow.transactions.add(txn)
            txn.created_at = created
            summary["transactions"] += 1

    async def _import_promocodes(
        self, uow: UnitOfWork, rows: list[dict[str, Any]], summary: dict[str, Any]
    ) -> None:
        for row in rows:
            code = str(row.get("code") or "").upper()
            if not code:
                continue
            ptype = str(row.get("type") or "").lower()
            bonus = _kopeks(row.get("balance_bonus_kopeks"))
            days = int(row.get("subscription_days") or 0)
            if bonus:
                reward, value = RewardType.BALANCE, bonus
            elif days:
                reward, value = RewardType.DURATION, days
            else:
                summary["skipped"].append(f"промокод {code}: тип {ptype!r} без награды — пропущен")
                continue

            promo = await uow.promocodes.find_one(code=code)
            if promo is None:
                promo = Promocode(code=code, reward_type=reward, reward_value=value)
                uow.session.add(promo)
            else:
                promo.reward_type, promo.reward_value = reward, value
            promo.is_active = bool(row.get("is_active"))
            promo.expires_at = _to_utc(row.get("valid_until"))
            promo.max_activations = row.get("max_uses")
            summary["promocodes"] += 1
