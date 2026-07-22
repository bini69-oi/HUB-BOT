"""OAuth 2.0 login for the web cabinet (Google, Yandex, VK ID).

Standard authorization-code flow; VK ID additionally requires PKCE (code_verifier /
code_challenge) and a device_id that VK appends to the callback. State is stored in
Redis as a JSON payload and consumed atomically (GETDEL — no TOCTOU replay). The
payload carries the provider, the PKCE verifier and, for the "link to my account"
mode, the id of the already-authenticated user.

Every provider yields a stable per-provider account id (``provider_id``), so a user
is first matched by (provider, provider_id) via ``linked_accounts`` and only then by
verified e-mail — VK accounts often have no e-mail at all and would otherwise be
impossible to log in. Config per provider: ``OAUTH_<P>_CLIENT_ID`` /
``OAUTH_<P>_CLIENT_SECRET``; the redirect URI is the cabinet URL itself.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass
from typing import Any

import httpx

from src.core.logging import get_logger

log = get_logger(__name__)

_STATE_PREFIX = "oauth_state:"
_STATE_TTL = 600


@dataclass(frozen=True, slots=True)
class OAuthUserInfo:
    provider_id: str
    email: str | None
    email_verified: bool
    name: str | None = None


def make_pkce_pair() -> tuple[str, str]:
    """(code_verifier, code_challenge) per RFC 7636, S256."""
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


class OAuthProvider:
    """One provider's endpoints + how to read its userinfo."""

    needs_pkce = False

    def __init__(self, name: str, client_id: str, client_secret: str) -> None:
        self.name = name
        self.client_id = client_id
        self.client_secret = client_secret

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def authorize_url(self, redirect_uri: str, state: str, code_challenge: str | None) -> str:
        raise NotImplementedError

    async def fetch_user(
        self,
        code: str,
        redirect_uri: str,
        *,
        code_verifier: str | None = None,
        device_id: str | None = None,
    ) -> OAuthUserInfo:
        raise NotImplementedError


class GoogleProvider(OAuthProvider):
    def authorize_url(self, redirect_uri: str, state: str, code_challenge: str | None) -> str:
        from urllib.parse import urlencode

        q = urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "access_type": "online",
            }
        )
        return f"https://accounts.google.com/o/oauth2/v2/auth?{q}"

    async def fetch_user(
        self,
        code: str,
        redirect_uri: str,
        *,
        code_verifier: str | None = None,
        device_id: str | None = None,
    ) -> OAuthUserInfo:
        async with httpx.AsyncClient(timeout=20) as http:
            tok = await http.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            access = str((tok.json() or {}).get("access_token") or "")
            if not access:
                raise ValueError("Google: no access_token")
            info = await http.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access}"},
            )
        data: dict[str, Any] = info.json() if info.status_code == 200 else {}
        email = str(data.get("email") or "")
        sub = str(data.get("sub") or "")
        if not email:
            raise ValueError("Google: no email in userinfo")
        return OAuthUserInfo(
            provider_id=sub or email.lower(),
            email=email.lower(),
            email_verified=bool(data.get("email_verified")),
            name=data.get("name"),
        )


class YandexProvider(OAuthProvider):
    def authorize_url(self, redirect_uri: str, state: str, code_challenge: str | None) -> str:
        from urllib.parse import urlencode

        q = urlencode(
            {
                "response_type": "code",
                "client_id": self.client_id,
                "redirect_uri": redirect_uri,
                "state": state,
            }
        )
        return f"https://oauth.yandex.ru/authorize?{q}"

    async def fetch_user(
        self,
        code: str,
        redirect_uri: str,
        *,
        code_verifier: str | None = None,
        device_id: str | None = None,
    ) -> OAuthUserInfo:
        async with httpx.AsyncClient(timeout=20) as http:
            tok = await http.post(
                "https://oauth.yandex.ru/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )
            access = str((tok.json() or {}).get("access_token") or "")
            if not access:
                raise ValueError("Yandex: no access_token")
            info = await http.get(
                "https://login.yandex.ru/info?format=json",
                headers={"Authorization": f"OAuth {access}"},
            )
        data: dict[str, Any] = info.json() if info.status_code == 200 else {}
        email = str(data.get("default_email") or "")
        uid = str(data.get("id") or "")
        if not email:
            raise ValueError("Yandex: no email")
        # Yandex accounts are phone/email-verified by the provider.
        return OAuthUserInfo(
            provider_id=uid or email.lower(),
            email=email.lower(),
            email_verified=True,
            name=data.get("real_name"),
        )


class VKProvider(OAuthProvider):
    """VK ID (id.vk.com), OAuth 2.1: PKCE is mandatory, the callback carries a
    device_id that must be echoed back on the token exchange. E-mail is optional —
    plenty of VK accounts have none, which is exactly why login is identity-first."""

    needs_pkce = True

    def authorize_url(self, redirect_uri: str, state: str, code_challenge: str | None) -> str:
        from urllib.parse import urlencode

        q = urlencode(
            {
                "response_type": "code",
                "client_id": self.client_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "code_challenge": code_challenge or "",
                "code_challenge_method": "S256",
                "scope": "email",
            }
        )
        return f"https://id.vk.com/authorize?{q}"

    async def fetch_user(
        self,
        code: str,
        redirect_uri: str,
        *,
        code_verifier: str | None = None,
        device_id: str | None = None,
    ) -> OAuthUserInfo:
        async with httpx.AsyncClient(timeout=20) as http:
            tok = await http.post(
                "https://id.vk.com/oauth2/auth",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "code_verifier": code_verifier or "",
                    "client_id": self.client_id,
                    "device_id": device_id or "",
                    "redirect_uri": redirect_uri,
                },
            )
            tdata: dict[str, Any] = tok.json() or {}
            access = str(tdata.get("access_token") or "")
            if not access:
                raise ValueError(f"VK: no access_token ({tdata.get('error_description') or ''})")
            info = await http.post(
                "https://id.vk.com/oauth2/user_info",
                data={"access_token": access, "client_id": self.client_id},
            )
        data: dict[str, Any] = (info.json() or {}).get("user") or {}
        uid = str(data.get("user_id") or tdata.get("user_id") or "")
        if not uid:
            raise ValueError("VK: no user_id in user_info")
        email = str(data.get("email") or "").lower() or None
        name = " ".join(p for p in (data.get("first_name"), data.get("last_name")) if p) or None
        # VK verifies the e-mail on its side before handing it out with the email scope.
        return OAuthUserInfo(provider_id=uid, email=email, email_verified=bool(email), name=name)


_PROVIDERS: dict[str, type[OAuthProvider]] = {
    "google": GoogleProvider,
    "yandex": YandexProvider,
    "vk": VKProvider,
}

PROVIDER_NAMES = tuple(_PROVIDERS)


def build_provider(name: str, client_id: str, client_secret: str) -> OAuthProvider | None:
    cls = _PROVIDERS.get(name)
    if cls is None:
        return None
    provider = cls(name, client_id, client_secret)
    return provider if provider.configured else None


async def save_state(redis: object, payload: dict[str, Any]) -> str:
    state = secrets.token_urlsafe(32)
    await redis.set(  # type: ignore[attr-defined]
        f"{_STATE_PREFIX}{state}", json.dumps(payload), ex=_STATE_TTL
    )
    return state


async def consume_state(redis: object, state: str) -> dict[str, Any] | None:
    """Atomic GETDEL — a state token is single-use (anti-replay)."""
    value = await redis.getdel(f"{_STATE_PREFIX}{state}")  # type: ignore[attr-defined]
    if value is None:
        return None
    try:
        data = json.loads(value)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None
