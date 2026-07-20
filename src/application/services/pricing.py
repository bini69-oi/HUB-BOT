"""PricingService — computes the final price with discount stacking (docs/context/04).

Order: base plan price (+ squad add-ons) -> effective promo-group % + period % -> personal +
one-shot purchase discount -> cap at 100%. A zero/100%-off result is a free purchase.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import select

from src.application.dto.pricing import PriceQuote, PurchaseRequest
from src.core.constants import MAX_DISCOUNT_PERCENT
from src.core.enums import Currency, PurchaseType
from src.core.exceptions import PurchaseError
from src.core.money import Money
from src.infrastructure.database.models.plan import Plan, PlanDuration, PlanPrice
from src.infrastructure.database.models.promo_group import PromoGroup, UserPromoGroup

if TYPE_CHECKING:
    from src.infrastructure.database.models.constructor import ConstructorPeriod, TrafficPack
    from src.infrastructure.database.uow import UnitOfWork


class PricingService:
    async def quote(self, uow: UnitOfWork, req: PurchaseRequest) -> PriceQuote:
        if req.purchase_type is PurchaseType.TRAFFIC_TOPUP:
            return await self._topup_quote(uow, req)
        if req.constructor_period_id is not None:
            # Constructor mode: price = period + traffic pack. The hidden service plan is
            # intentionally inactive, so the plan-catalogue checks below don't apply.
            period, pack = await self.resolve_constructor(uow, req)
            components = {"period": period.price_minor, "pack": pack.price_minor}
            base_total = Money(period.price_minor + pack.price_minor, req.currency)
        else:
            plan = await uow.plans.get(req.plan_id)
            if plan is None or not plan.is_active:
                raise PurchaseError(f"plan {req.plan_id} not found or inactive")

            base_minor = await self._base_price_minor(uow, plan, req)
            squads_minor = await self._squads_addon_minor(uow, req)
            components = {"plan": base_minor, "squads": squads_minor}
            base_total = Money(base_minor + squads_minor, req.currency)

        promo_pct = await self._promo_group_discount(uow, req)
        user = await uow.users.get(req.user_id)
        personal = user.personal_discount_pct if user else 0
        purchase = user.purchase_discount_pct if user else 0
        sale_pct, sale_id = await self._sale_discount(uow)

        discount_pct = min(MAX_DISCOUNT_PERCENT, promo_pct + personal + purchase + sale_pct)
        final = base_total.apply_discount(discount_pct)

        if req.purchase_type is PurchaseType.CHANGE and req.subscription_id is not None:
            # Plan switch (proration): the unused value of the current period is preserved as
            # BONUS DAYS on the new plan — converted at the new period's daily rate — instead of a
            # price discount. So the user never loses time, pays the full list price of the new
            # period, and their remaining money value carries over fairly across differently
            # priced plans. Purely informational for the quote; provisioning recomputes it.
            bonus = await self.change_bonus_days(uow, req)
            if bonus > 0:
                components["change_bonus_days"] = bonus

        return PriceQuote(
            base=base_total,
            discount_pct=discount_pct,
            final=final,
            components=components,
            sale_campaign_id=sale_id if sale_pct > 0 else None,
        )

    async def _sale_discount(self, uow: UnitOfWork) -> tuple[int, int | None]:
        """Best active limited-quantity sale: (discount_pct, campaign_id) or (0, None)."""
        sale = await uow.sales.active_now(dt.datetime.now(dt.UTC))
        return (sale.discount_pct, sale.id) if sale else (0, None)

    async def _topup_quote(self, uow: UnitOfWork, req: PurchaseRequest) -> PriceQuote:
        """Traffic top-up: the pack price with the user's discounts applied."""
        pack = (
            await uow.traffic_packs.get(req.traffic_pack_id)
            if req.traffic_pack_id is not None
            else None
        )
        if pack is None or not pack.is_active or pack.gb <= 0:
            raise PurchaseError("traffic pack not found or inactive")
        user = await uow.users.get(req.user_id)
        personal = user.personal_discount_pct if user else 0
        purchase = user.purchase_discount_pct if user else 0
        discount_pct = min(MAX_DISCOUNT_PERCENT, personal + purchase)
        base = Money(pack.price_minor, req.currency)
        return PriceQuote(
            base=base,
            discount_pct=discount_pct,
            final=base.apply_discount(discount_pct),
            components={"pack": pack.price_minor},
        )

    async def change_bonus_days(self, uow: UnitOfWork, req: PurchaseRequest) -> int:
        """Plan-change proration: the remaining days of the CURRENT plan converted to whole days
        of the NEW plan at their LIST daily rates.

        Computed from the subscription's own expiry and the two plans' catalogue prices — NOT from
        payment history. So it can't over-credit by extrapolating one short top-up across a long
        remainder, and can't silently drop the remainder when the provisioning payment scrolls out
        of a recent-transactions window. A remainder on a plan worth Ra/day carries as
        ``remaining * Ra / R_new`` days on the target plan. If either list rate is unknown we keep
        the raw remaining days (behaves like a renewal - the user never loses paid time).
        """
        if req.subscription_id is None:
            return 0
        sub = await uow.subscriptions.get(req.subscription_id)
        if sub is None or sub.expire_at is None or sub.is_trial or sub.plan_id is None:
            return 0
        remaining = (sub.expire_at - dt.datetime.now(dt.UTC)).total_seconds() / 86400
        if remaining <= 0:
            return 0
        # Value the remainder at the CURRENT plan's CHEAPEST per-day rate (its longest-duration
        # price): the user paid at least that, so this never over-credits — even when the plan
        # also lists a pricier short duration and the remainder came from an annual purchase.
        current_daily = await self._plan_min_daily_minor(uow, sub.plan_id, req.currency)
        new_daily = await self._new_period_daily_minor(uow, req)
        if current_daily <= 0 or new_daily <= 0:
            return round(remaining)  # pricing unknown → preserve remaining days (renewal-safe)
        return round(remaining * current_daily / new_daily)

    async def _plan_min_daily_minor(
        self, uow: UnitOfWork, plan_id: int, currency: Currency
    ) -> float:
        """A plan's CHEAPEST list price per day across all its durations (0 if it has no prices)."""
        rows = (
            await uow.session.execute(
                select(PlanDuration.days, PlanPrice.price_minor)
                .join(PlanPrice, PlanPrice.plan_duration_id == PlanDuration.id)
                .where(PlanDuration.plan_id == plan_id, PlanPrice.currency == currency)
            )
        ).all()
        rates = [int(p) / int(d) for d, p in rows if d and int(d) > 0]
        return min(rates) if rates else 0.0

    async def _new_period_daily_minor(self, uow: UnitOfWork, req: PurchaseRequest) -> float:
        """Per-day list price of the NEW period being bought (the plan's price for the purchased
        duration, or the constructor period+pack)."""
        if req.constructor_period_id is not None:
            period, pack = await self.resolve_constructor(uow, req)
            return (period.price_minor + pack.price_minor) / period.days if period.days else 0.0
        plan = await uow.plans.get(req.plan_id)
        if plan is None:
            return 0.0
        base = await self._base_price_minor(uow, plan, req)
        return base / req.duration_days if req.duration_days > 0 else 0.0

    async def resolve_constructor(
        self, uow: UnitOfWork, req: PurchaseRequest
    ) -> tuple[ConstructorPeriod, TrafficPack]:
        """Load and validate the constructor selection referenced by the request."""
        period = (
            await uow.constructor_periods.get(req.constructor_period_id)
            if req.constructor_period_id is not None
            else None
        )
        if period is None or not period.is_active:
            raise PurchaseError(f"constructor period {req.constructor_period_id} unavailable")
        pack = (
            await uow.traffic_packs.get(req.traffic_pack_id)
            if req.traffic_pack_id is not None
            else None
        )
        if pack is None or not pack.is_active:
            raise PurchaseError(f"traffic pack {req.traffic_pack_id} unavailable")
        if req.duration_days != period.days:
            raise PurchaseError("constructor request duration does not match the period")
        return period, pack

    async def _base_price_minor(self, uow: UnitOfWork, plan: Plan, req: PurchaseRequest) -> int:
        stmt = (
            select(PlanPrice.price_minor)
            .join(PlanDuration, PlanPrice.plan_duration_id == PlanDuration.id)
            .where(
                PlanDuration.plan_id == plan.id,
                PlanDuration.days == req.duration_days,
                PlanPrice.currency == req.currency,
            )
            .limit(1)
        )
        price = await uow.session.scalar(stmt)
        if price is None:
            raise PurchaseError(
                f"no price for plan={plan.id} days={req.duration_days} {req.currency.value}"
            )
        return int(price)

    async def _squads_addon_minor(self, uow: UnitOfWork, req: PurchaseRequest) -> int:
        # ServerSquad.price_minor is a single, currency-less column, so summing it into a
        # currency-specific base would mix currencies (e.g. RUB kopeks into a USD-cent base).
        # Squad add-on pricing is intentionally disabled until per-currency squad prices exist
        # (a plan_prices-style table). Returning 0 keeps charges correct; do NOT sum raw prices.
        return 0

    async def _promo_group_discount(self, uow: UnitOfWork, req: PurchaseRequest) -> int:
        """Highest-priority group the user belongs to; server % + this duration's period %."""
        stmt = (
            select(PromoGroup)
            .join(UserPromoGroup, UserPromoGroup.promo_group_id == PromoGroup.id)
            .where(UserPromoGroup.user_id == req.user_id)
            .order_by(PromoGroup.priority.desc())
            .limit(1)
        )
        group = await uow.session.scalar(stmt)
        if group is None:
            return 0
        period_pct = int(group.period_discounts.get(str(req.duration_days), 0))
        return group.server_discount_pct + period_pct
