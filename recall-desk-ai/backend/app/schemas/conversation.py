"""Conversation and message schemas."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.enums import MessageRole


class ConversationCreate(BaseModel):
    ticket_id: Optional[int] = None
    title: Optional[str] = Field(default=None, max_length=200)


class MessageCreate(BaseModel):
    role: MessageRole = MessageRole.user
    content: str = Field(min_length=1, max_length=20000)


class MessageRead(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ConversationRead(BaseModel):
    id: int
    customer_id: int
    ticket_id: Optional[int] = None
    session_id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    message_count: int = 0

    model_config = {"from_attributes": True}


class ConversationListResponse(BaseModel):
    items: List[ConversationRead]
    total: int
    limit: int
    offset: int


class ConversationDetail(ConversationRead):
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    messages: List[MessageRead] = Field(default_factory=list)
