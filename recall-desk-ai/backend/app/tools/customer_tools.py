"""Customer oriented agent tools."""

from __future__ import annotations

from typing import Any, Dict, List

from app.schemas.customer import CustomerRead
from app.schemas.ticket import TicketRead
from app.services.customer_service import CustomerService
from app.services.ticket_service import TicketService
from app.tools.registry import ToolDefinition

READ_ROLES = ("admin", "agent", "viewer")
WRITE_ROLES = ("admin", "agent")


def build_customer_tools(
    customers: CustomerService, tickets: TicketService
) -> List[ToolDefinition]:
    async def search_customer(query: str, limit: int = 5) -> Dict[str, Any]:
        if not query.strip():
            return {"customers": []}
        listing = await customers.list(search=query, limit=min(max(limit, 1), 20))
        return {
            "query": query,
            "customers": [CustomerRead.model_validate(c).model_dump(mode="json") for c in listing.items],
        }

    async def get_customer_tickets(customer_id: int, limit: int = 5) -> Dict[str, Any]:
        rows = await tickets.history(customer_id, limit=min(max(limit, 1), 20))
        return {
            "customer_id": customer_id,
            "tickets": [TicketRead.model_validate(t).model_dump(mode="json") for t in rows],
        }

    async def get_ticket_history(ticket_id: int) -> Dict[str, Any]:
        detail = await tickets.detail(ticket_id)
        return detail.model_dump(mode="json")

    return [
        ToolDefinition(
            name="search_customer",
            description=(
                "Search customers in your organization by name, email or company. "
                "Use this to find the account record for the person you are talking to."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Name, email or company fragment"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                },
                "required": ["query"],
            },
            handler=search_customer,
            roles=READ_ROLES,
        ),
        ToolDefinition(
            name="get_customer_tickets",
            description="List the most recent tickets for a customer with their status and priority.",
            parameters={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "integer"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                },
                "required": ["customer_id"],
            },
            handler=get_customer_tickets,
            roles=READ_ROLES,
        ),
        ToolDefinition(
            name="get_ticket_history",
            description="Get one ticket with its conversation count and every recorded resolution.",
            parameters={
                "type": "object",
                "properties": {"ticket_id": {"type": "integer"}},
                "required": ["ticket_id"],
            },
            handler=get_ticket_history,
            roles=READ_ROLES,
        ),
    ]
