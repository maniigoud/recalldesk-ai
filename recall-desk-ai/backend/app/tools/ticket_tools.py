"""Ticket mutation tools offered to the agent."""

from __future__ import annotations

from typing import Any, Dict, List

from app.schemas.ticket import ResolutionUpsert, TicketCreate, TicketRead, TicketUpdate
from app.services.ticket_service import TicketService
from app.tools.registry import ToolDefinition

WRITE_ROLES = ("admin", "agent")


def build_ticket_tools(tickets: TicketService) -> List[ToolDefinition]:
    async def create_ticket(
        customer_id: int,
        title: str,
        description: str = "",
        priority: str = "medium",
    ) -> Dict[str, Any]:
        payload = TicketCreate(
            customer_id=customer_id,
            title=title,
            description=description or None,
            priority=priority,  # type: ignore[arg-type]
        )
        ticket = await tickets.create(payload)
        return TicketRead.model_validate(ticket).model_dump(mode="json")

    async def update_ticket(
        ticket_id: int,
        status: str | None = None,
        priority: str | None = None,
        title: str | None = None,
        description: str | None = None,
        assigned_to: int | None = None,
    ) -> Dict[str, Any]:
        payload = TicketUpdate(
            status=status,  # type: ignore[arg-type]
            priority=priority,  # type: ignore[arg-type]
            title=title,
            description=description,
            assigned_to=assigned_to,
        )
        ticket = await tickets.update(ticket_id, payload)
        return TicketRead.model_validate(ticket).model_dump(mode="json")

    async def suggest_resolution(
        ticket_id: int,
        summary: str,
        solution: str,
        successful: bool = True,
    ) -> Dict[str, Any]:
        existing = await tickets.detail(ticket_id)
        payload = ResolutionUpsert(summary=summary, solution=solution, successful=successful)
        ticket = await tickets.update(
            existing.id,
            TicketUpdate(status=existing.status),  # type: ignore[arg-type]
            resolution=payload,
        )
        return {
            "ticket_id": ticket.id,
            "status": ticket.status,
            "resolution_recorded": True,
            "successful": successful,
        }

    return [
        ToolDefinition(
            name="create_ticket",
            description=(
                "Create a support ticket for a customer. Use this when a new problem is reported "
                "that is not already tracked."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "integer"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                        "default": "medium",
                    },
                },
                "required": ["customer_id", "title"],
            },
            handler=create_ticket,
            roles=WRITE_ROLES,
            write=True,
        ),
        ToolDefinition(
            name="update_ticket",
            description="Update an existing ticket's status, priority, title, description or assignee.",
            parameters={
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "integer"},
                    "status": {
                        "type": "string",
                        "enum": ["open", "investigating", "waiting", "resolved", "escalated"],
                    },
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "assigned_to": {"type": "integer"},
                },
                "required": ["ticket_id"],
            },
            handler=update_ticket,
            roles=WRITE_ROLES,
            write=True,
        ),
        ToolDefinition(
            name="suggest_resolution",
            description=(
                "Record a resolution on a ticket with a short summary and the solution steps that "
                "worked. Only call this when a fix is actually known to have worked."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "integer"},
                    "summary": {"type": "string"},
                    "solution": {"type": "string"},
                    "successful": {"type": "boolean", "default": True},
                },
                "required": ["ticket_id", "summary", "solution"],
            },
            handler=suggest_resolution,
            roles=WRITE_ROLES,
            write=True,
        ),
    ]
