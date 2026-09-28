"""Knowledge base and tool registry unit tests."""

from __future__ import annotations


from app.services.knowledge_base_service import knowledge_base
from app.tools.registry import ToolDefinition, ToolRegistry


def test_knowledge_base_contains_expected_documents():
    titles = {doc["title"] for doc in knowledge_base.list_documents()}
    assert {
        "API Authentication Guide",
        "Database Troubleshooting",
        "Deployment Runbook",
        "Rate Limit Policy",
        "Billing FAQ",
        "Incident Response Guide",
    } <= titles


def test_knowledge_base_search_ranks_relevant_document_first():
    results = knowledge_base.search("our API is timing out, connection pool", limit=3)
    assert results
    assert results[0]["id"] == "kb-database-troubleshooting"
    assert "connection pool" in results[0]["content"].lower()


def test_knowledge_base_search_returns_nothing_for_unrelated_query():
    assert knowledge_base.search("what is the weather on mars", limit=3) == []


def test_knowledge_base_document_lookup():
    doc = knowledge_base.get("kb-rate-limit-policy")
    assert doc is not None
    assert doc.category == "limits"
    assert knowledge_base.get("does-not-exist") is None


async def test_tool_registry_enforces_roles():
    async def handler() -> str:
        return "done"

    definition = ToolDefinition(
        name="write_thing",
        description="writes",
        parameters={"type": "object", "properties": {}},
        handler=handler,
        roles=("admin",),
        write=True,
    )

    viewer_registry = ToolRegistry(role="viewer")
    viewer_registry.register(definition)
    denied = await viewer_registry.execute("write_thing", {})
    assert denied["ok"] is False
    assert denied["error"] == "PERMISSION_DENIED"

    admin_registry = ToolRegistry(role="admin")
    admin_registry.register(definition)
    allowed = await admin_registry.execute("write_thing", {})
    assert allowed == {"ok": True, "result": "done"}


async def test_tool_registry_reports_unknown_and_invalid_calls():
    async def handler(customer_id: int) -> dict:
        return {"customer_id": customer_id}

    registry = ToolRegistry(role="agent")
    registry.register(
        ToolDefinition(
            name="get_customer",
            description="reads",
            parameters={
                "type": "object",
                "properties": {"customer_id": {"type": "integer"}},
                "required": ["customer_id"],
            },
            handler=handler,
        )
    )

    unknown = await registry.execute("nope", {})
    assert unknown["error"] == "UNKNOWN_TOOL"

    invalid = await registry.execute("get_customer", {"wrong": 1})
    assert invalid["ok"] is False


async def test_tool_registry_turns_handler_errors_into_results():
    async def handler() -> None:
        raise RuntimeError("database exploded")

    registry = ToolRegistry(role="agent")
    registry.register(
        ToolDefinition(
            name="boom",
            description="fails",
            parameters={"type": "object", "properties": {}},
            handler=handler,
        )
    )
    result = await registry.execute("boom", {})
    assert result["ok"] is False
    assert result["error"] == "TOOL_ERROR"
