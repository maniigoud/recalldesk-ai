"""Ticket and resolution schemas."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.enums import TicketPriority, TicketStatus


class TicketCreate(BaseModel):
    customer_id: int
    title: str = Field(min_length=3, max_length=255)
    description: Optional[str] = Field(default=None, max_length=20000)
    priority: TicketPriority = TicketPriority.medium
    status: TicketStatus = TicketStatus.open
    assigned_to: Optional[int] = None


class TicketUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=255)
    description: Optional[str] = Field(default=None, max_length=20000)
    priority: Optional[TicketPriority] = None
    status: Optional[TicketStatus] = None
    assigned_to: Optional[int] = None


class ResolutionUpsert(BaseModel):
    summary: str = Field(min_length=3, max_length=4000)
    solution: str = Field(min_length=3, max_length=20000)
    successful: bool = True


class TicketUpdateRequest(BaseModel):
    """Body for PUT /api/tickets/{id} - update fields and optionally a resolution."""

    ticket: TicketUpdate = Field(default_factory=TicketUpdate)
    resolution: Optional[ResolutionUpsert] = None


class ResolutionRead(BaseModel):
    id: int
    ticket_id: int
    summary: str
    solution: str
    successful: bool
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TicketRead(BaseModel):
    id: int
    customer_id: int
    title: str
    description: Optional[str] = None
    priority: str
    status: str
    assigned_to: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TicketListResponse(BaseModel):
    items: List[TicketRead]
    total: int
    limit: int
    offset: int


class TicketDetail(TicketRead):
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    assignee_name: Optional[str] = None
    conversation_count: int = 0
    resolutions: List[ResolutionRead] = Field(default_factory=list)
