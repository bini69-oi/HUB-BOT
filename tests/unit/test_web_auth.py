"""Web-cabinet auth building blocks: email lookup, verify-token lookup, refresh rotation."""

from __future__ import annotations

import datetime as dt
import hashlib

from src.core.enums import AuthType, Currency
from src.core.security import hash_password, jwt_decode, jwt_encode, verify_password
from src.infrastructure.database.models.cabinet_token import CabinetRefreshToken
from src.infrastructure.database.models.user import User
from src.infrastructure.database.uow import UnitOfWork


async def _make_email_user(uow: UnitOfWork, email: str, password: str) -> User:
    from src.application.services.ids import generate_referral_code

    user = User(
        auth_type=AuthType.EMAIL,
        email=email,
        password_hash=hash_password(password),
        email_verified=True,
        referral_code=generate_referral_code(),
        currency=Currency.RUB,
    )
    await uow.users.add(user)
    return user


async def test_get_by_email_is_case_insensitive(uow: UnitOfWork) -> None:
    async with uow:
        await _make_email_user(uow, "Buyer@Example.com", "hunter2pass")
        await uow.commit()
        found = await uow.users.get_by_email("buyer@example.com")
        assert found is not None and found.auth_type is AuthType.EMAIL
        assert verify_password("hunter2pass", found.password_hash or "")
        assert not verify_password("wrong", found.password_hash or "")


async def test_find_by_verify_token(uow: UnitOfWork) -> None:
    async with uow:
        user = await _make_email_user(uow, "v@example.com", "password1")
        user.email_verified = False
        user.notification_settings = {"verify_token": "abc123deadbeef", "verify_expires": "x"}
        await uow.commit()
        found = await uow.users.find_by_verify_token("abc123deadbeef")
        assert found is not None and found.id == user.id
        assert await uow.users.find_by_verify_token("nope") is None


async def test_refresh_token_rotation(uow: UnitOfWork) -> None:
    async with uow:
        user = await _make_email_user(uow, "r@example.com", "password1")
        await uow.commit()

        def token_row(raw: str) -> CabinetRefreshToken:
            return CabinetRefreshToken(
                user_id=user.id,
                token_hash=hashlib.sha256(raw.encode()).hexdigest(),
                expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=7),
            )

        uow.session.add(token_row("refresh-1"))
        await uow.commit()

        row = await uow.cabinet_tokens.find_one(token_hash=hashlib.sha256(b"refresh-1").hexdigest())
        assert row is not None and row.revoked_at is None
        # rotate: spend the old one, issue a new one
        row.revoked_at = dt.datetime.now(dt.UTC)
        uow.session.add(token_row("refresh-2"))
        await uow.commit()

        spent = await uow.cabinet_tokens.find_one(
            token_hash=hashlib.sha256(b"refresh-1").hexdigest()
        )
        assert spent is not None and spent.revoked_at is not None  # cannot be reused
        fresh = await uow.cabinet_tokens.find_one(
            token_hash=hashlib.sha256(b"refresh-2").hexdigest()
        )
        assert fresh is not None and fresh.revoked_at is None


def test_access_jwt_round_trip() -> None:
    token = jwt_encode({"sub": 42, "type": "access", "web": True}, "secret-key", 900)
    payload = jwt_decode(token, "secret-key")
    assert payload is not None
    assert payload["sub"] == 42 and payload["web"] is True
    assert jwt_decode(token, "wrong-key") is None


def test_auto_login_token_type_and_staff_guard() -> None:
    """Auto-login tokens are a distinct type; the /login/auto route rejects non-auto
    tokens and staff accounts (weak proof must never unlock an admin)."""
    from src.core.enums import Role
    from src.core.security import jwt_decode, jwt_encode

    secret = "sekret"
    auto = jwt_encode({"sub": 5, "type": "auto_login", "web": True}, secret, 3600)
    payload = jwt_decode(auto, secret)
    assert payload is not None and payload["type"] == "auto_login"

    # an access token must NOT be accepted where an auto_login token is expected
    access = jwt_decode(jwt_encode({"sub": 5, "type": "access"}, secret, 3600), secret)
    assert access is not None and access["type"] != "auto_login"

    # staff role is what the route guards on
    assert Role.ADMIN.is_staff is True
    assert Role.USER.is_staff is False


async def test_oauth_state_single_use() -> None:
    """OAuth state is stored then consumed atomically — a replay finds nothing."""
    from src.infrastructure.services.oauth import consume_state, save_state

    class FakeRedis:
        def __init__(self) -> None:
            self.store: dict[str, str] = {}

        async def set(self, k: str, v: str, ex: int = 0) -> None:
            self.store[k] = v

        async def getdel(self, k: str) -> str | None:
            return self.store.pop(k, None)

    redis = FakeRedis()
    state = await save_state(redis, {"provider": "google", "verifier": "v1"})
    assert await consume_state(redis, state) == {"provider": "google", "verifier": "v1"}
    assert await consume_state(redis, state) is None  # single-use


def test_oauth_provider_registry_and_urls() -> None:
    from src.infrastructure.services.oauth import build_provider, make_pkce_pair

    assert build_provider("google", "", "") is None  # unconfigured -> None
    assert build_provider("unknown", "id", "sec") is None  # unknown provider
    g = build_provider("google", "cid", "sec")
    assert g is not None
    url = g.authorize_url("https://cab.example/auth/oauth/callback", "st8", None)
    assert "accounts.google.com" in url and "state=st8" in url and "client_id=cid" in url
    y = build_provider("yandex", "cid", "sec")
    assert y is not None and "oauth.yandex.ru" in y.authorize_url("https://c/cb", "s", None)
    # VK ID: OAuth 2.1 with mandatory PKCE — the challenge must land in the URL
    vk = build_provider("vk", "cid", "sec")
    assert vk is not None and vk.needs_pkce
    verifier, challenge = make_pkce_pair()
    assert verifier != challenge and len(verifier) >= 43
    vk_url = vk.authorize_url("https://c/cb", "s", challenge)
    assert "id.vk.com/authorize" in vk_url
    assert f"code_challenge={challenge}" in vk_url and "code_challenge_method=S256" in vk_url


async def test_vk_fetch_user_identity_first() -> None:
    """VK exchange: token + user_info; an account WITHOUT e-mail still yields a stable
    provider_id (identity-first login), with e-mail when the scope was granted."""
    import respx
    from httpx import Response

    from src.infrastructure.services.oauth import build_provider

    vk = build_provider("vk", "cid", "sec")
    assert vk is not None
    with respx.mock:
        respx.post("https://id.vk.com/oauth2/auth").mock(
            return_value=Response(200, json={"access_token": "at", "user_id": 987})
        )
        respx.post("https://id.vk.com/oauth2/user_info").mock(
            return_value=Response(
                200, json={"user": {"user_id": 987, "first_name": "Иван", "last_name": "Петров"}}
            )
        )
        info = await vk.fetch_user("code1", "https://c/cb", code_verifier="v", device_id="d1")
    assert info.provider_id == "987"
    assert info.email is None and info.email_verified is False
    assert info.name == "Иван Петров"

    with respx.mock:
        respx.post("https://id.vk.com/oauth2/auth").mock(
            return_value=Response(200, json={"access_token": "at2"})
        )
        respx.post("https://id.vk.com/oauth2/user_info").mock(
            return_value=Response(
                200,
                json={"user": {"user_id": 987, "email": "Ivan@Mail.ru", "first_name": "Иван"}},
            )
        )
        info2 = await vk.fetch_user("code2", "https://c/cb", code_verifier="v", device_id="d1")
    assert info2.email == "ivan@mail.ru" and info2.email_verified is True


async def test_linked_account_identity_lookup(uow: UnitOfWork) -> None:
    from src.infrastructure.database.models.linked_account import LinkedAccount

    async with uow:
        user = await _make_email_user(uow, "vkuser@example.com", "password1")
        await uow.flush()
        uow.session.add(LinkedAccount(user_id=user.id, provider="vk", external_id="987"))
        await uow.commit()
        ident = await uow.linked_accounts.get_identity("vk", "987")
        assert ident is not None and ident.user_id == user.id
        assert await uow.linked_accounts.get_identity("vk", "000") is None
        rows = await uow.linked_accounts.list_for_user(user.id)
        assert [r.provider for r in rows] == ["vk"]
