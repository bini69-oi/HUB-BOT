"""Platega (app.platega.io) — SBP / card / crypto, hosted redirect.

Ported from a battle-tested integration (methods verified live: 2=SBP QR,
11=card acquiring, 13=crypto). Auth is the X-MerchantId + X-Secret header pair on
BOTH our requests and their callback — the callback is verified by comparing those
headers against our credentials (constant-time). Platega generates the transaction
id itself, so the webhook matches by ``external_id``.

Settings row keys: ``merchant_id``, ``secret`` (Fernet-encrypted at rest),
optional ``payment_method`` (2 default).
"""

from __future__ import annotations

import hmac
from decimal import Decimal
from typing import Any

import httpx

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
from src.infrastructure.payments.base import BasePaymentGateway

log = get_logger(__name__)

API = "https://app.platega.io"

_PAID = {"CONFIRMED"}
_CLOSED = {"CANCELED", "CANCELLED", "CHARGEBACKED", "EXPIRED", "REJECTED", "FAILED"}

# Buyer-facing form -> Platega provider method id (2=SBP QR, 11=card acquiring, 13=crypto).
# When several forms are enabled the owner offers each as its own payment button; the chosen
# form arrives in the context metadata and selects the method here.
_FORM_METHOD = {"sbp": 2, "card": 11, "crypto": 13}


class PlategaGateway(BasePaymentGateway):
    gateway_type = PaymentGatewayType.PLATEGA

    @property
    def capabilities(self) -> GatewayCapabilities:
        return GatewayCapabilities(currencies=frozenset({Currency.RUB}), needs_http_webhook=True)

    def _creds(self) -> tuple[str, str]:
        mid = str(self.settings.get("merchant_id") or "")
        secret = str(self.settings.get("secret") or "")
        if not mid or not secret:
            raise PaymentError("Platega: merchant_id/secret not configured")
        return mid, secret

    def _headers(self) -> dict[str, str]:
        mid, secret = self._creds()
        return {"X-MerchantId": mid, "X-Secret": secret}

    def _method_id(self, ctx: PaymentContext) -> int:
        # The buyer's chosen form (metadata['form']) wins; else the configured default; else SBP.
        form = ctx.metadata.get("form")
        if form and form in _FORM_METHOD:
            return _FORM_METHOD[form]
        return int(self.settings.get("payment_method") or 2)

    async def create_payment(self, ctx: PaymentContext) -> PaymentResult:
        value = float((Decimal(ctx.amount.amount_minor) / 100).quantize(Decimal("0.01")))
        payload: dict[str, Any] = {
            "paymentMethod": self._method_id(ctx),
            "paymentDetails": {"amount": value, "currency": ctx.amount.currency.value},
            "description": (ctx.description or "VPN subscription")[:128],
            "return": ctx.return_url or "https://t.me",
            "failedUrl": ctx.return_url or "https://t.me",
        }
        async with httpx.AsyncClient(timeout=20) as http:
            res = await http.post(
                f"{API}/transaction/process", json=payload, headers=self._headers()
            )
        if res.status_code not in (200, 201):
            log.error("platega create failed", status=res.status_code, body=res.text[:300])
            raise PaymentError(f"Platega error {res.status_code}")
        data = res.json()
        txid = str(data.get("transactionId") or data.get("id") or "")
        url = str(data.get("redirect") or data.get("redirectUrl") or data.get("url") or "")
        if not txid or not url:
            raise PaymentError("Platega: unexpected response (no transactionId/redirect)")
        return PaymentResult(kind=PaymentResultKind.REDIRECT, external_id=txid, redirect_url=url)

    def _verify(self, request: WebhookRequest) -> None:
        mid, secret = self._creds()
        headers = {k.lower(): v for k, v in request.headers.items()}
        got_mid = str(headers.get("x-merchantid") or "")
        got_sec = str(headers.get("x-secret") or "")
        if not (hmac.compare_digest(got_mid, mid) and hmac.compare_digest(got_sec, secret)):
            raise WebhookVerificationError("Platega: bad credentials in callback headers")

    @staticmethod
    def _map_status(status: str) -> TransactionStatus:
        status = status.strip().upper()
        if status in _PAID:
            return TransactionStatus.COMPLETED
        if status in _CLOSED:
            return TransactionStatus.CANCELED
        return TransactionStatus.PENDING

    async def handle_webhook(self, request: WebhookRequest) -> WebhookResult:
        self._verify(request)
        body = self.parse_json(request.body)
        return WebhookResult(
            status=self._map_status(str(body.get("status") or "")),
            external_id=str(body.get("id") or "") or None,
        )

    async def fetch_status(self, external_id: str) -> WebhookResult | None:
        try:
            async with httpx.AsyncClient(timeout=15) as http:
                res = await http.get(f"{API}/transaction/{external_id}", headers=self._headers())
        except httpx.HTTPError:
            return None
        if res.status_code != 200:
            return None
        status = self._map_status(str(res.json().get("status") or ""))
        if status is TransactionStatus.PENDING:
            return None
        return WebhookResult(status=status, external_id=external_id)
