"""Pydantic schemas for memory (Hindsight) endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

MemoryType = Literal["world", "experience", "observation"]


class MemoryRecord(BaseModel):
    """Frontend friendly normalization of a Hindsight memory fact.

    Every field is either returned by the Hindsight API or safely derived
    from metadata that RecallDesk attached at retain time.
    """

    id: str
    content: str
    type: str
    customer_id: Optional[int] = None
    source: str = "hindsight"
    relevance: Optional[float] = None
    created_at: Optional[datetime] = None
    occurred_start: Optional[datetime] = None
    occurred_end: Optional[datetime] = None
    context: Optional[str] = None
    document_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, str] = Field(default_factory=dict)
    scores: Dict[str, Any] = Field(default_factory=dict)


class MemoryListResponse(BaseModel):
    items: List[MemoryRecord]
    total: int
    limit: int
    offset: int
    provider: str


class RecallRequest(BaseModel):
    customer_id: int
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=10, ge=1, le=50)
    types: Optional[List[MemoryType]] = None
    budget: Optional[Literal["low", "mid", "high"]] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    @field_validator("query")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value


class RecallResponse(BaseModel):
    customer_id: int
    query: str
    memories: List[MemoryRecord]
    count: int
    provider: str
    demo_mode: bool = False
    duration_ms: int = 0


class RetainRequest(BaseModel):
    customer_id: int
    content: str = Field(min_length=1, max_length=20000)
    context: Optional[str] = Field(default=None, max_length=200)
    conversation_id: Optional[int] = None
    document_id: Optional[str] = Field(default=None, max_length=120)
    timestamp: Optional[datetime] = None
    metadata: Dict[str, str] = Field(default_factory=dict)

    @field_validator("content")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content must not be blank")
        return value


class RetainResponse(BaseModel):
    customer_id: int
    retained: bool
    provider: str
    demo_mode: bool = False
    document_id: Optional[str] = None
    duration_ms: int = 0


class ReflectRequest(BaseModel):
    customer_id: int
    query: str = Field(min_length=1, max_length=2000)
    budget: Optional[Literal["low", "mid", "high"]] = None

    @field_validator("query")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value


class MemoryReference(BaseModel):
    id: str
    content: str
    type: str


class ReflectResponse(BaseModel):
    customer_id: int
    query: str
    answer: str
    memories_used: List[MemoryReference]
    provider: str
    demo_mode: bool = False
    duration_ms: int = 0
