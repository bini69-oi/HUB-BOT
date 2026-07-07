"""Robokassa — card/SBP, the classic redirect checkout with MD5 signatures.

Create: a signed link to auth.robokassa.ru (InvId=0, our uuid travels in Shp_pid —
custom Shp params are part of the signature). ResultURL: form-encoded fields, the
signature is ``md5(OutSum:InvId:password2:Shp_pid=...)`` and the mandatory plain-text
acknowledgement ``OK{InvId}`` is carried by ``WebhookResult.http_body``.

Settings row keys: ``merchant_login``, ``password1``, ``password2``
(Fernet-encrypted at rest), optional ``is_test`` ("1" for the sandbox).
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
from decimal import Decimal
from urllib.parse import parse_qsl, urlencode

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

PAY_URL = "https://auth.robokassa.ru/Merchant/Index.aspx"


def _md5(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()


class RobokassaGateway(BasePaymentGateway):
    gateway_type = PaymentGatewayType.ROBOKASSA

    @property
    def capabilities(self) -> GatewayCapabilities:
        return GatewayCapabilities(currencies=frozenset({Currency.RUB}), needs_http_webhook=True)

    def _creds(self) -> tuple[str, str, str]:
        login = str(self.settings.get("merchant_login") or "")
        p1 = str(self.settings.get("password1") or "")
        p2 = str(self.settings.get("password2") or "")
        if not login or not p1 or not p2:
            raise PaymentError("Robokassa: merchant_login/password1/password2 not configured")
        return login, p1, p2

    async def create_payment(self, ctx: PaymentContext) -> PaymentResult:
        login, p1, _ = self._creds()
        out_sum = str((Decimal(ctx.amount.amount_minor) / 100).quantize(Decimal("0.01")))
        shp = f"Shp_pid={ctx.payment_id}"
        signature = _md5(f"{login}:{out_sum}:0:{p1}:{shp}")
        params = {
            "MerchantLogin": login,
            "OutSum": out_sum,
            "InvId": "0",
            "Description": (ctx.description or "VPN subscription")[:100],
            "SignatureValue": signature,
            "Shp_pid": str(ctx.payment_id),
        }
        if str(self.settings.get("is_test") or "") in ("1", "true"):
            params["IsTest"] = "1"
        return PaymentResult(
            kind=PaymentResultKind.REDIRECT,
            external_id=str(ctx.payment_id),  # InvId=0: our uuid IS the anchor
            redirect_url=f"{PAY_URL}?{urlencode(params)}",
        )

    async def handle_webhook(self, request: WebhookRequest) -> WebhookResult:
        _, _, p2 = self._creds()
        fields = dict(parse_qsl(request.body.decode("utf-8", "replace")))
        out_sum = fields.get("OutSum") or ""
        inv_id = fields.get("InvId") or "0"
        pid = fields.get("Shp_pid") or ""
        got = (fields.get("SignatureValue") or "").lower()
        expected = _md5(f"{out_sum}:{inv_id}:{p2}:Shp_pid={pid}").lower()
        if not got or not hmac.compare_digest(got, expected):
            raise WebhookVerificationError("Robokassa: signature mismatch")

        from uuid import UUID

        payment_id = None
        with contextlib.suppress(ValueError):
            payment_id = UUID(pid)
        amount = None
        with contextlib.suppress(ArithmeticError):
            amount = Money(int(Decimal(out_sum) * 100), Currency.RUB)
        return WebhookResult(
            status=TransactionStatus.COMPLETED,
            payment_id=payment_id,
            external_id=pid or None,
            amount=amount,
            http_body=f"OK{inv_id}",  # mandatory exact plain-text ACK
        )
