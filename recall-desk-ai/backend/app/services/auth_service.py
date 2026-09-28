"""Authentication service: registration, login and user lookup."""

from __future__ import annotations

from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AuthenticationError, ConflictError
from app.core.logging import get_logger
from app.core.security import create_access_token, hash_password, verify_password
from app.models.organization import Organization
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserRead

logger = get_logger(__name__)


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user_by_email(self, email: str) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def get_user(self, user_id: int) -> Optional[User]:
        return await self.session.get(User, user_id)

    async def register(self, payload: RegisterRequest) -> Tuple[User, str]:
        email = payload.email.lower()
        if await self.get_user_by_email(email):
            raise ConflictError(
                "A user with this email already exists.", code="EMAIL_ALREADY_EXISTS"
            )

        organization = Organization(name=payload.organization_name, industry=payload.industry)
        self.session.add(organization)
        await self.session.flush()

        user = User(
            name=payload.name,
            email=email,
            password_hash=hash_password(payload.password),
            role=payload.role.value,
            organization_id=organization.id,
        )
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)

        logger.info(
            "auth.register",
            extra={"user_id": user.id, "organization_id": organization.id},
        )
        return user, self._issue_token(user)

    async def login(self, payload: LoginRequest) -> Tuple[User, str]:
        user = await self.get_user_by_email(payload.email.lower())
        if not user or not verify_password(payload.password, user.password_hash):
            logger.warning("auth.login_failed", extra={"email": payload.email.lower()})
            raise AuthenticationError("Invalid email or password.")

        logger.info("auth.login", extra={"user_id": user.id, "role": user.role})
        return user, self._issue_token(user)

    def _issue_token(self, user: User) -> str:
        return create_access_token(
            subject=str(user.id),
            role=user.role,
            organization_id=user.organization_id,
        )

    @staticmethod
    def token_response(user: User, token: str) -> TokenResponse:
        return TokenResponse(
            access_token=token,
            expires_in=settings.access_token_expire_minutes * 60,
            user=UserRead.model_validate(user),
        )
