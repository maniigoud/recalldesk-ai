"""Agent pipeline tests (require MySQL).

Groq and Hindsight are replaced by deterministic fakes so the pipeline itself
is exercised end to end without external credentials.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence

import pytest
from httpx import AsyncClient

from app.api.deps import get_llm, get_memory_service
from app.main import app
from app.services.hindsight_service import DemoMemoryProvider, HindsightService
from app.services.llm_service import LLMResponse, ToolCall

pytestmark = pytest.mark.db


class ScriptedLLM:
    """Minimal LLM double: one tool round trip, then a final answer."""

    name = "scripted"
    model = "scripted-model"
    is_demo = False

    def __init__(self) -> None:
        self.calls: List[List[Dict[str, Any]]] = []

    async def complete(self, *, messages, tools=None, temperature: float = 0.2) -> LLMResponse:
        self.calls.append(list(messages))
        system = messages[0].get("content", "")

        if "extract durable support memory" in system:
            return LLMResponse(
                content=json.dumps(
                    {
                        "memories": [
                            {
                                "type": "fact",
                                "content": "Arjun Technologies runs its API on AWS RDS with PostgreSQL 16.",
                            },
                            {
                                "type": "fact",
                                "content": "Arjun Technologies has an RDS connection limit of 100.",
                            },
                        ]
                    }
                ),
                model=self.model,
            )

        if tools and not any(message.get("role") == "tool" for message in messages):
            return LLMResponse(
                content="",
                model=self.model,
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="get_customer_tickets",
                        arguments={"customer_id": _customer_id_from(messages)},
                    )
                ],
            )

        return LLMResponse(
            content=(
                "This looks similar to the timeout your team hit before. Your API is on "
                "PostgreSQL 16 on RDS with a connection limit of 100."
            ),
            model=self.model,
        )

    async def health(self) -> str:
        return "connected"


def _customer_id_from(messages: Sequence[Dict[str, Any]]) -> int:
    blob = " ".join(str(message.get("content", "")) for message in messages)
    marker = "Arjun"
    assert marker in blob
    return _ACTIVE_CUSTOMER_ID


_ACTIVE_CUSTOMER_ID = 1


@pytest.fixture
def fake_providers():
    llm = ScriptedLLM()
    memory = HindsightService(DemoMemoryProvider())
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[get_memory_service] = lambda: memory
    yield llm, memory
    app.dependency_overrides.clear()


async def _customer(auth_client: AsyncClient) -> dict:
    response = await auth_client.post(
        "/api/customers",
        json={
            "name": "Arjun Mehta",
            "email": "arjun@arjuntech.example",
            "company": "Arjun Technologies",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_chat_persists_messages_and_retains_memory(
    auth_client: AsyncClient, fake_providers
):
    llm, memory = fake_providers
    customer = await _customer(auth_client)
    global _ACTIVE_CUSTOMER_ID
    _ACTIVE_CUSTOMER_ID = customer["id"]

    first = await auth_client.post(
        "/api/support/chat",
        json={
            "customer_id": customer["id"],
            "message": "We're deploying our API to AWS RDS using PostgreSQL 16. "
            "Our connection limit is 100.",
        },
    )
    assert first.status_code == 200, first.text
    body = first.json()

    assert body["memories_recalled"] == 0
    assert body["memory_retained"] is True
    assert "get_customer_tickets" in body["tools_used"]
    assert body["model"] == "scripted-model"
    assert body["agent_run_id"]

    messages = await auth_client.get(
        f"/api/conversations/{body['conversation_id']}/messages"
    )
    assert [m["role"] for m in messages.json()] == ["user", "assistant"]

    dashboard = await auth_client.get("/api/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["agent_run_count"] >= 1
    assert dashboard.json()["memory_retain_count"] >= 1


async def test_new_session_recalls_persistent_memory(
    auth_client: AsyncClient, fake_providers
):
    llm, memory = fake_providers
    customer = await _customer(auth_client)
    global _ACTIVE_CUSTOMER_ID
    _ACTIVE_CUSTOMER_ID = customer["id"]

    session_one = await auth_client.post(
        "/api/support/chat",
        json={
            "customer_id": customer["id"],
            "message": "We're deploying our API to AWS RDS using PostgreSQL 16. "
            "Our connection limit is 100.",
        },
    )
    assert session_one.json()["memory_retained"] is True

    session_two = await auth_client.post(
        "/api/support/chat",
        json={
            "customer_id": customer["id"],
            "message": "Our API is timing out again.",
        },
    )
    body = session_two.json()

    assert body["conversation_id"] != session_one.json()["conversation_id"]
    assert body["session_id"] != session_one.json()["session_id"]
    assert body["memories_recalled"] >= 1
    assert any(
        "PostgreSQL" in memory_item["content"] for memory_item in body["recalled_memories"]
    )

    # The new session transcript is empty of the old conversation.
    messages = await auth_client.get(
        f"/api/conversations/{body['conversation_id']}/messages"
    )
    assert len(messages.json()) == 2
    assert messages.json()[0]["content"] == "Our API is timing out again."


async def test_agent_run_and_memory_events_are_recorded(
    auth_client: AsyncClient, fake_providers
):
    customer = await _customer(auth_client)
    global _ACTIVE_CUSTOMER_ID
    _ACTIVE_CUSTOMER_ID = customer["id"]

    response = await auth_client.post(
        "/api/support/chat",
        json={"customer_id": customer["id"], "message": "We deploy on Kubernetes."},
    )
    assert response.status_code == 200

    analytics = await auth_client.get("/api/analytics")
    body = analytics.json()
    assert body["agent_runs"] >= 1
    assert body["memory_recalls"] >= 1
    assert 0.0 <= body["resolution_rate"] <= 1.0


async def test_chat_for_unknown_customer_returns_404(
    auth_client: AsyncClient, fake_providers
):
    response = await auth_client.post(
        "/api/support/chat", json={"customer_id": 999999, "message": "hello"}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CUSTOMER_NOT_FOUND"
