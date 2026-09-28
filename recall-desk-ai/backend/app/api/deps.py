"""FastAPI dependencies: authentication, authorization and service wiring."""

from __future__ import annotations

from typing import Annotated, AsyncIterator, Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthenticationError, AuthorizationError
from app.core.security import decode_access_token
from app.db.database import get_session
from app.models.user import User
from app.services.agent_service import AgentService
from app.services.analytics_service import AnalyticsService
from app.services.auth_service import AuthService
from app.services.conversation_service import ConversationService
from app.services.customer_service import CustomerService
from app.services.hindsight_service import HindsightService, get_hindsight_service
from app.services.llm_service import LLMService, get_llm_service
from app.services.ticket_service import TicketService

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")


async def db_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    session: AsyncSession = Depends(db_session),
) -> User:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Authentication credentials were not provided.")

    payload = decode_access_token(credentials.credentials)
    try:
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError) as exc:
        raise AuthenticationError("Access token subject is invalid.") from exc

    user = await session.get(User, user_id)
    if not user:
        raise AuthenticationError("The account for this token no longer exists.")
    if payload.get("organization_id") != user.organization_id:
        raise AuthenticationError("Token organization does not match this account.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: str):
    async def dependency(user: User = Depends(get_current_user)) -> User:
        if roles and user.role not in roles:
            raise AuthorizationError(
                f"This action requires one of these roles: {', '.join(roles)}."
            )
        return user

    return dependency


# --- service dependencies -------------------------------------------------


def get_auth_service(session: AsyncSession = Depends(db_session)) -> AuthService:
    return AuthService(session)


def get_memory_service() -> HindsightService:
    return get_hindsight_service()


def get_llm() -> LLMService:
    return get_llm_service()


def get_customer_service(
    session: AsyncSession = Depends(db_session),
    user: User = Depends(get_current_user),
    memory: HindsightService = Depends(get_memory_service),
) -> CustomerService:
    return CustomerService(session, user.organization_id, memory=memory)


def get_ticket_service(
    session: AsyncSession = Depends(db_session),
    user: User = Depends(get_current_user),
) -> TicketService:
    return TicketService(session, user.organization_id)


def get_conversation_service(
    session: AsyncSession = Depends(db_session),
    user: User = Depends(get_current_user),
) -> ConversationService:
    return ConversationService(session, user.organization_id)


def get_analytics_service(
    session: AsyncSession = Depends(db_session),
    user: User = Depends(get_current_user),
    memory: HindsightService = Depends(get_memory_service),
    llm: LLMService = Depends(get_llm),
) -> AnalyticsService:
    return AnalyticsService(
        session,
        user.organization_id,
        memory_provider=memory.provider_name,
        llm_configured=not llm.is_demo,
    )


def get_agent_service(
    session: AsyncSession = Depends(db_session),
    user: User = Depends(get_current_user),
    memory: HindsightService = Depends(get_memory_service),
    llm: LLMService = Depends(get_llm),
) -> AgentService:
    organization_id = user.organization_id
    return AgentService(
        session=session,
        organization_id=organization_id,
        user_id=user.id,
        role=user.role,
        conversations=ConversationService(session, organization_id),
        customers=CustomerService(session, organization_id, memory=memory),
        tickets=TicketService(session, organization_id),
        memory=memory,
        llm=llm,
    )
