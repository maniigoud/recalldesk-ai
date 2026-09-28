"""Memory (Hindsight) endpoints for the Memory Explorer."""

from __future__ import annotations

import time
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, db_session, get_memory_service
from app.core.errors import NotFoundError
from app.models.customer import Customer
from app.models.enums import MemoryOperation
from app.models.memory_event import MemoryEvent
from app.schemas.memory import (
    MemoryListResponse,
    RecallRequest,
    RecallResponse,
    ReflectRequest,
    ReflectResponse,
    RetainRequest,
    RetainResponse,
)
from app.services.hindsight_service import HindsightService

router = APIRouter(tags=["Memory"])


async def _assert_customer(session: AsyncSession, organization_id: int, customer_id: int) -> Customer:
    result = await session.execute(
        select(Customer).where(
            Customer.id == customer_id, Customer.organization_id == organization_id
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise NotFoundError("Customer was not found.", code="CUSTOMER_NOT_FOUND")
    return customer


@router.get(
    "/api/customers/{customer_id}/memories",
    response_model=MemoryListResponse,
    summary="Browse a customer's stored memories",
)
async def list_customer_memories(
    customer_id: int,
    memory: Annotated[HindsightService, Depends(get_memory_service)],
    session: Annotated[AsyncSession, Depends(db_session)],
    user: CurrentUser,
    search: Optional[str] = Query(default=None),
    memory_type: Optional[str] = Query(default=None, description="world | experience | observation"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> MemoryListResponse:
    await _assert_customer(session, user.organization_id, customer_id)
    page = await memory.list_memories(
        customer_id=customer_id,
        search=search,
        memory_type=memory_type,
        limit=limit,
        offset=offset,
    )
    return MemoryListResponse(provider=memory.provider_name, **page)


@router.post("/api/memory/recall", response_model=RecallResponse, summary="Recall memories")
async def recall(
    payload: RecallRequest,
    memory: Annotated[HindsightService, Depends(get_memory_service)],
    session: Annotated[AsyncSession, Depends(db_session)],
    user: CurrentUser,
) -> RecallResponse:
    await _assert_customer(session, user.organization_id, payload.customer_id)
    started = time.perf_counter()
    outcome = await memory.recall(
        customer_id=payload.customer_id,
        organization_id=user.organization_id,
        query=payload.query,
        limit=payload.limit,
        types=list(payload.types) if payload.types else None,
        budget=payload.budget,
    )
    session.add(
        MemoryEvent(
            customer_id=payload.customer_id,
            operation=MemoryOperation.recall.value,
            query=payload.query,
            memory_count=len(outcome.memories),
            provider=memory.provider_name,
        )
    )
    await session.flush()
    return RecallResponse(
        customer_id=payload.customer_id,
        query=payload.query,
        memories=outcome.memories,
        count=len(outcome.memories),
        provider=outcome.provider,
        demo_mode=memory.is_demo,
        duration_ms=outcome.duration_ms or int((time.perf_counter() - started) * 1000),
    )


@router.post(
    "/api/memory/retain",
    response_model=RetainResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Retain information into customer memory",
)
async def retain(
    payload: RetainRequest,
    memory: Annotated[HindsightService, Depends(get_memory_service)],
    session: Annotated[AsyncSession, Depends(db_session)],
    user: CurrentUser,
) -> RetainResponse:
    await _assert_customer(session, user.organization_id, payload.customer_id)
    outcome = await memory.retain(
        customer_id=payload.customer_id,
        organization_id=user.organization_id,
        content=payload.content,
        context=payload.context,
        document_id=payload.document_id,
        conversation_id=payload.conversation_id,
        timestamp=payload.timestamp,
        metadata=payload.metadata,
    )
    session.add(
        MemoryEvent(
            customer_id=payload.customer_id,
            conversation_id=payload.conversation_id,
            operation=MemoryOperation.retain.value,
            query=payload.content[:2000],
            memory_count=1,
            provider=memory.provider_name,
        )
    )
    await session.flush()
    return RetainResponse(
        customer_id=payload.customer_id,
        retained=outcome.retained,
        provider=outcome.provider,
        demo_mode=memory.is_demo,
        document_id=outcome.document_id,
        duration_ms=int(outcome.details.get("duration_ms", 0)),
    )


@router.post("/api/memory/reflect", response_model=ReflectResponse, summary="Reflect over memory")
async def reflect(
    payload: ReflectRequest,
    memory: Annotated[HindsightService, Depends(get_memory_service)],
    session: Annotated[AsyncSession, Depends(db_session)],
    user: CurrentUser,
) -> ReflectResponse:
    await _assert_customer(session, user.organization_id, payload.customer_id)
    outcome = await memory.reflect(
        customer_id=payload.customer_id,
        organization_id=user.organization_id,
        query=payload.query,
        budget=payload.budget,
    )
    session.add(
        MemoryEvent(
            customer_id=payload.customer_id,
            operation=MemoryOperation.reflect.value,
            query=payload.query,
            memory_count=len(outcome.memories_used),
            provider=memory.provider_name,
        )
    )
    await session.flush()
    return ReflectResponse(
        customer_id=payload.customer_id,
        query=payload.query,
        answer=outcome.answer,
        memories_used=outcome.memories_used,
        provider=outcome.provider,
        demo_mode=memory.is_demo,
        duration_ms=outcome.duration_ms,
    )
