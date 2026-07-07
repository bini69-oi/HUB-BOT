"""YooMoney (personal wallet) — quickpay link + HTTP notification with a sha1 hash.

Create is just a signed quickpay URL (no API calls). The notification is form-encoded;
sha1 over nine fields with ``notification_secret`` (from the wallet settings).
IMPORTANT: ``amount`` in the notification is AFTER fees, and the user can technically
edit the sum in the form — the pipeline cross-checks it against the transaction price
(see the PaymentService underpayment gate). ``label`` = our payment_id.

Settings row keys: ``wallet``, ``notification_secret`` (Fernet-encrypted at rest).
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
from decimal import Decimal
from urllib.parse import parse_qsl, urlencode
from uuid import UUID

from src.application.common.payments import (
    GatewayCapabilities,
    PaymentContext,
    PaymentResult,
    PaymentResultKind,
    WebhookRequest,
    WebhookResult,
)
from src.core.enums import Currency, PaymentGatewayType, TransactionStatus
from src.core.exceptions import PaymentError, WebhookVerificationError
from src.core.logging import get_logger
from src.core.money import Money
from src.infrastructure.payments.base import BasePaymentGateway

log = get_logger(__name__)

QUICKPAY = "https://yoomoney.ru/quickpay/confirm"


class YoomoneyGateway(BasePaymentGateway):
    gateway_type = PaymentGatewayType.YOOMONEY

    @property
    def capabilities(self) -> GatewayCapabilities:
        return GatewayCapabilities(currencies=frozenset({Currency.RUB}), needs_http_webhook=True)

    def _creds(self) -> tuple[str, str]:
        wallet = str(self.settings.get("wallet") or "")
        secret = str(self.settings.get("notification_secret") or "")
        if not wallet or not secret:
            raise PaymentError("YooMoney: wallet/notification_secret not configured")
        return wallet, secret

    async def create_payment(self, ctx: PaymentContext) -> PaymentResult:
        wallet, _ = self._creds()
        params = {
            "receiver": wallet,
            "quickpay-form": "shop",
            "paymentType": "AC",  # bank card; SB pays from the YooMoney balance
            "sum": str((Decimal(ctx.amount.amount_minor) / 100).quantize(Decimal("0.01"))),
            "label": str(ctx.payment_id),
            "targets": (ctx.description or "VPN subscription")[:100],
            "successURL": ctx.return_url or "https://t.me",
        }
        return PaymentResult(
            kind=PaymentResultKind.REDIRECT,
            external_id=str(ctx.payment_id),
            redirect_url=f"{QUICKPAY}?{urlencode(params)}",
        )

    async def handle_webhook(self, request: WebhookRequest) -> WebhookResult:
        _, secret = self._creds()
        f = dict(parse_qsl(request.body.decode("utf-8", "replace")))
        joined = "&".join(
            [
                f.get("notification_type", ""),
                f.get("operation_id", ""),
                f.get("amount", ""),
                f.get("currency", ""),
                f.get("datetime", ""),
                f.get("sender", ""),
                f.get("codepro", ""),
                secret,
                f.get("label", ""),
            ]
        )
        expected = hashlib.sha1(joined.encode()).hexdigest()
        got = (f.get("sha1_hash") or "").lower()
        if not got or not hmac.compare_digest(got, expected.lower()):
            raise WebhookVerificationError("YooMoney: sha1 mismatch")
        if f.get("codepro", "false").lower() == "true" or f.get("unaccepted") == "true":
            # protected/unaccepted transfer — the money is not ours yet
            return WebhookResult(status=TransactionStatus.PENDING)

        payment_id = None
        with contextlib.suppress(ValueError):
            payment_id = UUID(f.get("label") or "")
        amount = None
        with contextlib.suppress(ArithmeticError):
            amount = Money(int(Decimal(f.get("amount") or "0") * 100), Currency.RUB)
        return WebhookResult(
            status=TransactionStatus.COMPLETED,
            payment_id=payment_id,
            external_id=f.get("operation_id") or None,
            amount=amount,
        )
