"""Panel webhook signature verification — must fail closed on an empty secret."""

from __future__ import annotations

import hashlib
import hmac

import pytest

from src.core.exceptions import WebhookVerificationError
from src.infrastructure.remnawave.webhook import WebhookVerifier

BODY = b'{"event":"user.disabled","data":{"uuid":"x"}}'


def _sig(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_empty_secret_fails_closed() -> None:
    verifier = WebhookVerifier("")  # an empty-key HMAC is attacker-computable
    with pytest.raises(WebhookVerificationError):
        verifier.verify(BODY, {"x-remnawave-signature": _sig("", BODY)})


def test_valid_signature_passes() -> None:
    verifier = WebhookVerifier("s3cret")
    verifier.verify(BODY, {"x-remnawave-signature": _sig("s3cret", BODY)})  # no raise


def test_bad_signature_rejected() -> None:
    verifier = WebhookVerifier("s3cret")
    with pytest.raises(WebhookVerificationError):
        verifier.verify(BODY, {"x-remnawave-signature": "deadbeef"})
