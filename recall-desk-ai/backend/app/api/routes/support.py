"""AI support chat endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, get_agent_service
from app.schemas.support import SupportChatRequest, SupportChatResponse
from app.services.agent_service import AgentService

router = APIRouter(prefix="/api/support", tags=["AI Support"])


@router.post(
    "/chat",
    response_model=SupportChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Send a customer message to the memory aware support agent",
    description=(
        "Runs the full pipeline: store the message, recall relevant Hindsight memories, "
        "load MySQL customer/ticket context, call Groq with tools, store the reply, and "
        "retain durable information back into Hindsight."
    ),
)
async def chat(
    payload: SupportChatRequest,
    agent: Annotated[AgentService, Depends(get_agent_service)],
    user: CurrentUser,
) -> SupportChatResponse:
    return await agent.run_chat(
        customer_id=payload.customer_id,
        message=payload.message,
        conversation_id=payload.conversation_id,
        ticket_id=payload.ticket_id,
        persist=payload.persist,
    )
