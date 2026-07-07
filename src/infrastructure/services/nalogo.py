"""NalogGO (МойНалог / lknpd.nalog.ru) — fiscal receipts for self-employed sellers.

Registers each paid subscription as income via the «Мой налог» API and returns the
public receipt link. Off by default — needs the seller's INN + a device token (obtained
once via the app/registration flow). Failures are retried by the taskiq queue, never
block fulfilment.

Settings row keys (bot-config): ``NALOGO_ENABLED``, ``NALOGO_INN``, ``NALOGO_TOKEN``
(device token, Fernet-encrypted), ``NALOGO_SERVICE_NAME``.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import httpx

from src.core.logging import get_logger

log = get_logger(__name__)

API = "https://lknpd.nalog.ru/api/v1"
_MSK = dt.timezone(dt.timedelta(hours=3))


class NalogoError(Exception):
    """The receipt could not be registered — the caller should retry later."""


class NalogoClient:
    def __init__(self, inn: str, token: str, service_name: str = "Доступ к VPN-сервису") -> None:
        self._inn = inn
        self._token = token
        self._service_name = service_name

    async def register_income(self, amount_minor: int, *, name: str | None = None) -> str:
        """Register income and return the public receipt URL (print link)."""
        if not self._inn or not self._token:
            raise NalogoError("NalogGO: inn/token not configured")
        amount = float((Decimal(amount_minor) / 100).quantize(Decimal("0.01")))
        now = dt.datetime.now(_MSK).replace(microsecond=0)
        payload = {
            "paymentType": "CASH",
            "ignoreMaxTotalIncomeRestriction": False,
            "client": {
                "contactPhone": None,
                "displayName": None,
                "incomeType": "FROM_INDIVIDUAL",
                "inn": None,
            },
            "requestTime": now.isoformat(),
            "operationTime": now.isoformat(),
            "services": [{"name": name or self._service_name, "amount": amount, "quantity": 1}],
            "totalAmount": amount,
        }
        try:
            async with httpx.AsyncClient(timeout=20) as http:
                res = await http.post(
                    f"{API}/income",
                    json=payload,
                    headers={"Authorization": f"Bearer {self._token}"},
                )
        except httpx.HTTPError as exc:
            raise NalogoError(f"NalogGO network error: {exc}") from exc
        if res.status_code != 200:
            log.error("nalogo income failed", status=res.status_code, body=res.text[:300])
            raise NalogoError(f"NalogGO HTTP {res.status_code}")
        receipt_id = str((res.json() or {}).get("approvedReceiptUuid") or "")
        if not receipt_id:
            raise NalogoError("NalogGO: no receipt id in response")
        return f"https://lknpd.nalog.ru/api/v1/receipt/{self._inn}/{receipt_id}/print"
