"""Stdlib-only security primitives for the admin cabinet: scrypt hashes + HS256 JWT.

No new dependencies: password hashing uses ``hashlib.scrypt`` (16 MiB, interactive
profile), tokens are plain HS256 JWTs signed with ``APP__JWT_SECRET``. Constant-time
comparisons everywhere.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

# --- password hashing (scrypt) ------------------------------------------------

_SCRYPT_N = 2**14  # 16 MiB — interactive login profile
_SCRYPT_R = 8
_SCRYPT_P = 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N,
        _SCRYPT_R,
        _SCRYPT_P,
        base64.urlsafe_b64encode(salt).decode().rstrip("="),
        base64.urlsafe_b64encode(dk).decode().rstrip("="),
    )


def _b64pad(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(
            password.encode(),
            salt=_b64pad(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=32,
        )
        return hmac.compare_digest(dk, _b64pad(hash_b64))
    except (ValueError, TypeError):
        return False


# --- HS256 JWT ------------------------------------------------------------------


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def jwt_encode(payload: dict[str, Any], secret: str, ttl_seconds: int) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    body = dict(payload)
    now = int(time.time())
    body.setdefault("iat", now)
    body.setdefault("exp", now + ttl_seconds)
    head_b64 = _b64(json.dumps(header, separators=(",", ":")).encode())
    body_b64 = _b64(json.dumps(body, separators=(",", ":")).encode())
    signing = f"{head_b64}.{body_b64}"
    sig = hmac.new(secret.encode(), signing.encode(), hashlib.sha256).digest()
    return f"{signing}.{_b64(sig)}"


def validate_init_data(
    init_data: str, bot_token: str, *, max_age_seconds: int = 24 * 3600
) -> dict[str, Any] | None:
    """Verify Telegram Mini Apps initData (HMAC per Bot API docs); returns parsed fields.

    Secret key = HMAC_SHA256(key="WebAppData", msg=bot_token); hash = HMAC_SHA256 of the
    sorted key=value lines. Returns None on bad signature or stale auth_date.
    """
    from urllib.parse import parse_qsl

    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    except ValueError:
        return None
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        return None
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        return None
    if auth_date and time.time() - auth_date > max_age_seconds:
        return None
    if "user" in pairs:
        try:
            pairs["user_parsed"] = json.loads(pairs["user"])
        except json.JSONDecodeError:
            return None
    return pairs


def jwt_decode(token: str, secret: str) -> dict[str, Any] | None:
    """Verify signature + expiry; returns the payload or None."""
    try:
        head_b64, body_b64, sig_b64 = token.split(".")
        signing = f"{head_b64}.{body_b64}"
        expected = hmac.new(secret.encode(), signing.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64pad(sig_b64)):
            return None
        payload: dict[str, Any] = json.loads(_b64pad(body_b64))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
