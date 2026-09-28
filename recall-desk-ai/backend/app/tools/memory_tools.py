"""Memory tool: lets the agent pull extra customer context on demand."""

from __future__ import annotations

from typing import Any, Dict, List

from app.services.hindsight_service import HindsightService
from app.tools.registry import ToolDefinition

READ_ROLES = ("admin", "agent", "viewer")


def build_memory_tools(
    memory: HindsightService, organization_id: int
) -> List[ToolDefinition]:
    async def recall_customer_memory(
        customer_id: int, query: str, limit: int = 5
    ) -> Dict[str, Any]:
        outcome = await memory.recall(
            customer_id=customer_id,
            organization_id=organization_id,
            query=query,
            limit=min(max(limit, 1), 10),
        )
        return {
            "customer_id": customer_id,
            "query": query,
            "provider": outcome.provider,
            "memories": [
                {
                    "id": item.id,
                    "content": item.content,
                    "type": item.type,
                    "relevance": item.relevance,
                    "occurred_start": item.occurred_start.isoformat() if item.occurred_start else None,
                }
                for item in outcome.memories
            ],
        }

    return [
        ToolDefinition(
            name="recall_customer_memory",
            description=(
                "Search what we already know about a customer: their stack, preferences, "
                "previous incidents and what fixed them. Call this when the automatic recall "
                "was not enough for the question being asked."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "integer"},
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
                },
                "required": ["customer_id", "query"],
            },
            handler=recall_customer_memory,
            roles=READ_ROLES,
        )
    ]
