"""Manual gateway webhook parsing/verification (ADR-0004)."""

from __future__ import annotations

import uuid

import orjson
import pytest

from src.application.common.payments import WebhookRequest
from src.core.enums import TransactionStatus
from src.core.exceptions import WebhookVerificationError
from src.infrastructure.payments.gateways.manual import ManualGateway

_SECRET = "s3cr3t"
_HDR = {"x-admin-secret": _SECRET}


def _req(payload: dict[str, object], headers: dict[str, str] | None = None) -> WebhookRequest:
    return WebhookRequest(body=orjson.dumps(payload), headers=headers or {})


async def test_confirm_completes_payment() -> None:
    gateway = ManualGateway({"secret": _SECRET})
    pid = uuid.uuid4()
    result = await gateway.handle_webhook(_req({"payment_id": str(pid), "status": "confirm"}, _HDR))
    assert result.status is TransactionStatus.COMPLETED
    assert result.payment_id == pid


async def test_reject_cancels_payment() -> None:
    gateway = ManualGateway({"secret": _SECRET})
    pid = uuid.uuid4()
    result = await gateway.handle_webhook(_req({"payment_id": str(pid), "status": "reject"}, _HDR))
    assert result.status is TransactionStatus.CANCELED


async def test_missing_payment_id_is_rejected() -> None:
    gateway = ManualGateway({"secret": _SECRET})
    with pytest.raises(WebhookVerificationError):
        await gateway.handle_webhook(_req({"status": "confirm"}, _HDR))


async def test_no_secret_fails_closed() -> None:
    """Without a configured secret the public webhook must reject everything (fail-closed),
    else anyone could complete any pending payment by its uuid."""
    gateway = ManualGateway({})
    pid = uuid.uuid4()
    with pytest.raises(WebhookVerificationError):
        await gateway.handle_webhook(_req({"payment_id": str(pid), "status": "confirm"}))


async def test_admin_secret_is_enforced() -> None:
    gateway = ManualGateway({"secret": _SECRET})
    pid = uuid.uuid4()
    with pytest.raises(WebhookVerificationError):
        await gateway.handle_webhook(_req({"payment_id": str(pid)}, {"x-admin-secret": "wrong"}))
    ok = await gateway.handle_webhook(_req({"payment_id": str(pid)}, _HDR))
    assert ok.status is TransactionStatus.COMPLETED
