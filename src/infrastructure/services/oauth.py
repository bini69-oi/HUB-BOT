"""OAuth 2.0 login for the web cabinet (Google, Yandex).

Standard authorization-code flow. State is stored in Redis and consumed atomically
(GETDEL — no TOCTOU replay). We trust the provider's e-mail and link/create the local
account by that verified e-mail, so there are no extra per-provider id columns to keep
in sync. Config per provider: ``OAUTH_<P>_CLIENT_ID`` / ``OAUTH_<P>_CLIENT_SECRET``;
the redirect URI is ``<CABINET_URL>/auth/oauth/callback``.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

import httpx

from src.core.logging import get_logger

log = get_logger(__name__)

_STATE_PREFIX = "oauth_state:"
_STATE_TTL = 600


@dataclass(frozen=True, slots=True)
class OAuthUserInfo:
    email: str
    email_verified: bool
    name: str | None = None


class OAuthProvider:
    """One provider's endpoints + how to read its userinfo."""

    def __init__(self, name: str, client_id: str, client_secret: str) -> None:
        self.name = name
        self.client_id = client_id
        self.client_secret = client_secret

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def authorize_url(self, redirect_uri: str, state: str) -> str:
        raise NotImplementedError

    async def fetch_user(self, code: str, redirect_uri: str) -> OAuthUserInfo:
        raise NotImplementedError


class GoogleProvider(OAuthProvider):
    def authorize_url(self, redirect_uri: str, state: str) -> str:
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

    async def fetch_user(self, code: str, redirect_uri: str) -> OAuthUserInfo:
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
        data = info.json() if info.status_code == 200 else {}
        email = str(data.get("email") or "")
        if not email:
            raise ValueError("Google: no email in userinfo")
        return OAuthUserInfo(
            email=email.lower(),
            email_verified=bool(data.get("email_verified")),
            name=data.get("name"),
        )


class YandexProvider(OAuthProvider):
    def authorize_url(self, redirect_uri: str, state: str) -> str:
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

    async def fetch_user(self, code: str, redirect_uri: str) -> OAuthUserInfo:
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
        data = info.json() if info.status_code == 200 else {}
        email = str(data.get("default_email") or "")
        if not email:
            raise ValueError("Yandex: no email")
        # Yandex accounts are phone/email-verified by the provider.
        return OAuthUserInfo(email=email.lower(), email_verified=True, name=data.get("real_name"))


_PROVIDERS: dict[str, type[OAuthProvider]] = {
    "google": GoogleProvider,
    "yandex": YandexProvider,
}


def build_provider(name: str, client_id: str, client_secret: str) -> OAuthProvider | None:
    cls = _PROVIDERS.get(name)
    if cls is None:
        return None
    provider = cls(name, client_id, client_secret)
    return provider if provider.configured else None


async def save_state(redis: object, provider: str) -> str:
    state = secrets.token_urlsafe(32)
    await redis.set(f"{_STATE_PREFIX}{state}", provider, ex=_STATE_TTL)  # type: ignore[attr-defined]
    return state


async def consume_state(redis: object, state: str) -> str | None:
    """Atomic GETDEL — a state token is single-use (anti-replay)."""
    value = await redis.getdel(f"{_STATE_PREFIX}{state}")  # type: ignore[attr-defined]
    return str(value) if value is not None else None
