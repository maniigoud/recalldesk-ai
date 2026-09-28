"""Dashboard and analytics schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.ticket import TicketRead


class MemoryActivityPoint(BaseModel):
    date: str
    retains: int
    recalls: int
    reflects: int


class AgentActivity(BaseModel):
    conversation_id: int
    session_id: Optional[str] = None
    customer_name: Optional[str] = None
    model: str
    latency_ms: int
    tokens: int
    status: str
    created_at: Optional[datetime] = None


class DashboardResponse(BaseModel):
    organization_name: Optional[str] = None
    customer_count: int
    open_ticket_count: int
    resolved_ticket_count: int
    escalated_ticket_count: int
    conversation_count: int
    agent_run_count: int
    memory_event_count: int
    memory_recall_count: int
    memory_retain_count: int
    memory_reflect_count: int
    memory_provider: str
    llm_configured: bool
    memory_activity: List[MemoryActivityPoint] = Field(default_factory=list)
    recent_tickets: List[TicketRead] = Field(default_factory=list)
    recent_support_activity: List[AgentActivity] = Field(default_factory=list)
    generated_at: datetime


class CategoryCount(BaseModel):
    category: str
    count: int


class AnalyticsResponse(BaseModel):
    total_tickets: int
    open_tickets: int
    resolved_tickets: int
    escalated_tickets: int
    resolution_rate: float
    average_resolution_hours: Optional[float] = None
    agent_runs: int
    successful_agent_runs: int
    average_agent_latency_ms: Optional[float] = None
    total_tokens: int
    memory_recalls: int
    memory_retains: int
    memory_reflects: int
    customers: int
    conversations: int
    tickets_by_status: Dict[str, int] = Field(default_factory=dict)
    tickets_by_priority: Dict[str, int] = Field(default_factory=dict)
    recurring_issue_categories: List[CategoryCount] = Field(default_factory=list)
    generated_at: datetime
