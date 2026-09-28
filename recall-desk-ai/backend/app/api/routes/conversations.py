"""Conversation endpoints.

Starting a new conversation creates a new session_id. It never deletes or
overwrites the customer's persistent Hindsight memory.
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, get_conversation_service
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetail,
    ConversationListResponse,
    ConversationRead,
    MessageCreate,
    MessageRead,
)
from app.services.conversation_service import ConversationService

router = APIRouter(tags=["Conversations"])


@router.get(
    "/api/customers/{customer_id}/conversations",
    response_model=ConversationListResponse,
    summary="List a customer's conversation sessions",
)
async def list_customer_conversations(
    customer_id: int,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
    user: CurrentUser,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ConversationListResponse:
    return await service.list_for_customer(customer_id, limit=limit, offset=offset)


@router.post(
    "/api/customers/{customer_id}/conversations",
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new conversation session for a customer",
)
async def create_conversation(
    customer_id: int,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
    user: CurrentUser,
    payload: Optional[ConversationCreate] = None,
) -> ConversationRead:
    conversation = await service.create(customer_id, payload)
    return ConversationRead.model_validate(conversation)


@router.get(
    "/api/conversations/{conversation_id}",
    response_model=ConversationDetail,
    summary="Conversation detail with its messages",
)
async def get_conversation(
    conversation_id: int,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
    user: CurrentUser,
) -> ConversationDetail:
    return await service.detail(conversation_id)


@router.get(
    "/api/conversations/{conversation_id}/messages",
    response_model=List[MessageRead],
    summary="Messages of one conversation session",
)
async def list_messages(
    conversation_id: int,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
    user: CurrentUser,
) -> List[MessageRead]:
    return await service.list_messages(conversation_id)


@router.post(
    "/api/conversations/{conversation_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Append a message to a conversation",
)
async def add_message(
    conversation_id: int,
    payload: MessageCreate,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
    user: CurrentUser,
) -> MessageRead:
    message = await service.add_message(conversation_id, payload.content, payload.role)
    return MessageRead.model_validate(message)
