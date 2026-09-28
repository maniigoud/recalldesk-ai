"""AI support chat schemas."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.memory import MemoryRecord


class SupportChatRequest(BaseModel):
    customer_id: int
    conversation_id: Optional[int] = Field(
        default=None,
        description="Existing conversation. Omit to start a new session.",
    )
    message: str = Field(min_length=1, max_length=20000)
    ticket_id: Optional[int] = None
    persist: bool = Field(
        default=True,
        description="Set to false for a read-only preview (no messages/memory written).",
    )


class ToolUsage(BaseModel):
    name: str
    arguments_summary: Optional[str] = None


class SupportChatResponse(BaseModel):
    conversation_id: int
    session_id: str
    message: str
    memories_recalled: int
    memory_retained: bool
    memory_provider: str
    llm_provider: str
    model: str
    tools_used: List[str] = Field(default_factory=list)
    tool_details: List[ToolUsage] = Field(default_factory=list)
    recalled_memories: List[MemoryRecord] = Field(default_factory=list)
    retained_summary: Optional[str] = None
    demo_mode: bool = False
    warnings: List[str] = Field(default_factory=list)
    agent_run_id: Optional[int] = None
    latency_ms: int = 0
    tokens: int = 0
