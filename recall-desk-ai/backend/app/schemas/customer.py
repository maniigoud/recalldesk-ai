"""Customer schemas."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field

from app.schemas.memory import MemoryRecord


class CustomerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    company: Optional[str] = Field(default=None, max_length=200)
    status: str = "active"


class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    email: Optional[EmailStr] = None
    company: Optional[str] = Field(default=None, max_length=200)
    status: Optional[str] = None


class CustomerRead(BaseModel):
    id: int
    organization_id: int
    name: str
    email: str
    company: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CustomerListResponse(BaseModel):
    items: List[CustomerRead]
    total: int
    limit: int
    offset: int


class RecentTicket(BaseModel):
    id: int
    title: str
    status: str
    priority: str
    created_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CustomerDetail(CustomerRead):
    ticket_count: int = 0
    open_ticket_count: int = 0
    resolved_ticket_count: int = 0
    conversation_count: int = 0
    message_count: int = 0
    memory_count: int = 0
    memory_count_capped: bool = False
    memory_provider: str = "unknown"
    recent_tickets: List[RecentTicket] = Field(default_factory=list)
    recent_memories: List[MemoryRecord] = Field(default_factory=list)
