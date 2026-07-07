"""Wata (wata.pro) — card / SBP / TPay / SberPay, hosted payment links.

Create: POST /api/h2h/links (Bearer), ``orderId`` = our payment_id, the response
carries ``url`` + ``id``. Webhook: JSON body signed with RSA-SHA512, base64 signature
in the ``X-Signature`` header over the RAW body; the public key comes from
GET /api/h2h/public-key and is cached on the class.

Settings row keys: ``api_token`` (Fernet-encrypted at rest).
"""

from __future__ import annotations

import base64
import contextlib
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

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

API = "https://api.wata.pro/api/h2h"

_STATUS = {
    "paid": TransactionStatus.COMPLETED,
    "declined": TransactionStatus.CANCELED,
}


class WataGateway(BasePaymentGateway):
    gateway_type = PaymentGatewayType.WATA

    _public_key_pem: str | None = None

    @property
    def capabilities(self) -> GatewayCapabilities:
        return GatewayCapabilities(currencies=frozenset({Currency.RUB}), needs_http_webhook=True)

    def _token(self) -> str:
        token = str(self.settings.get("api_token") or "")
        if not token:
            raise PaymentError("Wata: api_token not configured")
        return token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token()}"}

    async def create_payment(self, ctx: PaymentContext) -> PaymentResult:
        payload: dict[str, Any] = {
            "amount": float((Decimal(ctx.amount.amount_minor) / 100).quantize(Decimal("0.01"))),
            "currency": ctx.amount.currency.value,
            "type": "OneTime",
            "description": (ctx.description or "VPN subscription")[:100],
            "orderId": str(ctx.payment_id),
            "successRedirectUrl": ctx.return_url or "https://t.me",
            "failRedirectUrl": ctx.return_url or "https://t.me",
        }
        async with httpx.AsyncClient(timeout=20) as http:
            res = await http.post(f"{API}/links", json=payload, headers=self._headers())
        if res.status_code not in (200, 201):
            log.error("wata create failed", status=res.status_code, body=res.text[:300])
            raise PaymentError(f"Wata error {res.status_code}")
        data = res.json()
        if not data.get("url"):
            raise PaymentError("Wata: no payment url in response")
        return PaymentResult(
            kind=PaymentResultKind.REDIRECT,
            external_id=str(data.get("id") or ""),
            redirect_url=str(data["url"]),
        )

    async def _public_key(self) -> str:
        if self._public_key_pem is None:
            async with httpx.AsyncClient(timeout=15) as http:
                res = await http.get(f"{API}/public-key", headers=self._headers())
            if res.status_code != 200:
                raise WebhookVerificationError(f"Wata: public key fetch failed {res.status_code}")
            data = res.json() if "json" in res.headers.get("content-type", "") else {}
            type(self)._public_key_pem = str(
                (data.get("value") if isinstance(data, dict) else None) or res.text
            )
        return self._public_key_pem or ""

    async def handle_webhook(self, request: WebhookRequest) -> WebhookResult:
        headers = {k.lower(): v for k, v in request.headers.items()}
        signature = headers.get("x-signature", "")
        if not signature:
            raise WebhookVerificationError("Wata: no X-Signature header")
        pem = await self._public_key()
        try:
            key = load_pem_public_key(pem.encode())
            if not isinstance(key, RSAPublicKey):
                raise TypeError("expected an RSA public key")
            key.verify(
                base64.b64decode(signature), request.body, padding.PKCS1v15(), hashes.SHA512()
            )
        except Exception as exc:
            raise WebhookVerificationError("Wata: signature verification failed") from exc

        body = self.parse_json(request.body)
        status = _STATUS.get(
            str(body.get("transactionStatus") or "").lower(), TransactionStatus.PENDING
        )
        payment_id = None
        with contextlib.suppress(ValueError):
            payment_id = UUID(str(body.get("orderId") or ""))
        return WebhookResult(
            status=status,
            payment_id=payment_id,
            external_id=str(body.get("transactionId") or body.get("id") or "") or None,
        )

    async def fetch_status(self, external_id: str) -> WebhookResult | None:
        try:
            async with httpx.AsyncClient(timeout=15) as http:
                res = await http.get(f"{API}/transactions/{external_id}", headers=self._headers())
        except httpx.HTTPError:
            return None
        if res.status_code != 200:
            return None
        data = res.json()
        status = _STATUS.get(str(data.get("status") or "").lower())
        if status is None:
            return None
        payment_id = None
        with contextlib.suppress(ValueError):
            payment_id = UUID(str(data.get("orderId") or ""))
        return WebhookResult(status=status, payment_id=payment_id, external_id=external_id)
