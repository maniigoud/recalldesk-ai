"""Knowledge base search tool (company documentation, not customer memory)."""

from __future__ import annotations

from typing import Any, Dict, List

from app.services.knowledge_base_service import knowledge_base
from app.tools.registry import ToolDefinition

READ_ROLES = ("admin", "agent", "viewer")


def build_knowledge_tools() -> List[ToolDefinition]:
    async def search_knowledge_base(query: str, limit: int = 3) -> Dict[str, Any]:
        results = knowledge_base.search(query, limit=min(max(limit, 1), 5))
        return {
            "query": query,
            "source": "knowledge_base",
            "documents": [
                {
                    "id": doc["id"],
                    "title": doc["title"],
                    "category": doc["category"],
                    "relevance": doc["relevance"],
                    "excerpt": doc["content"][:1200],
                }
                for doc in results
            ],
        }

    return [
        ToolDefinition(
            name="search_knowledge_base",
            description=(
                "Search RecallDesk's own product documentation (authentication, database "
                "troubleshooting, deployment, rate limits, billing, incident response). "
                "Use for 'how do I' questions about our product. Do not use it to look up "
                "facts about a specific customer."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to look up in our docs"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 5, "default": 3},
                },
                "required": ["query"],
            },
            handler=search_knowledge_base,
            roles=READ_ROLES,
        )
    ]
