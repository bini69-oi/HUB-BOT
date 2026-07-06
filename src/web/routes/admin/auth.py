"""Admin auth: username/password login -> JWT; bootstrap superadmin at startup."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.core.enums import AuthType, Role, UserStatus
from src.core.security import hash_password, jwt_encode, verify_password
from src.infrastructure.database.models.user import User
from src.infrastructure.di import AppContainer
from src.web.deps import get_container
from src.web.routes.admin.deps import AdminIdentity, require_admin

router = APIRouter(prefix="/auth")


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class LoginOut(BaseModel):
    token: str
    username: str
    role: str


@router.post("/login", response_model=LoginOut)
async def login(body: LoginIn, container: AppContainer = Depends(get_container)) -> LoginOut:
    async with container.uow() as uow:
        user = await uow.users.find_one(username=body.username.lstrip("@"))
    if (
        user is None
        or not user.role.is_staff
        or user.status is not UserStatus.ACTIVE
        or not user.password_hash
        or not verify_password(body.password, user.password_hash)
    ):
        # One error for both unknown user and bad password — no username probing.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    settings = container.settings
    token = jwt_encode(
        {"sub": user.id, "scope": "admin", "role": user.role.name},
        settings.app.jwt_secret,
        ttl_seconds=settings.admin.session_ttl_hours * 3600,
    )
    return LoginOut(token=token, username=user.username or f"id{user.id}", role=user.role.name)


class MeOut(BaseModel):
    user_id: int
    username: str
    role: str


@router.get("/me", response_model=MeOut)
async def me(identity: AdminIdentity = Depends(require_admin)) -> MeOut:
    return MeOut(user_id=identity.user_id, username=identity.username, role=identity.role.name)


async def bootstrap_admin(container: AppContainer) -> None:
    """Ensure the env-configured superadmin exists (called from app lifespan).

    ``ADMIN__USERNAME`` + ``ADMIN__PASSWORD`` create/update an OWNER-role account with
    email auth. No-op when either is empty. Password is only (re)hashed when it does not
    verify against the stored hash, so restarts don't rewrite the row.
    """
    username = container.settings.admin.username.strip().lstrip("@")
    password = container.settings.admin.password
    if not username or not password:
        return

    async with container.uow() as uow:
        user = await uow.users.find_one(username=username)
        if user is None:
            from src.application.services.ids import generate_referral_code

            user = User(
                username=username,
                auth_type=AuthType.EMAIL,
                role=Role.OWNER,
                referral_code=generate_referral_code(),
                password_hash=hash_password(password),
            )
            await uow.users.add(user)
        else:
            if not user.role.is_staff:
                user.role = Role.OWNER
            if not user.password_hash or not verify_password(password, user.password_hash):
                user.password_hash = hash_password(password)
        await uow.commit()
