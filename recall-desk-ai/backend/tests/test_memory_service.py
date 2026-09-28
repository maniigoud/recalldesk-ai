"""Memory service tests: the demo provider and provider error handling."""

from __future__ import annotations

import pytest

from app.core.errors import HindsightError
from app.schemas.memory import MemoryRecord
from app.services.hindsight_service import (
    DemoMemoryProvider,
    HindsightService,
    MemoryProvider,
)


class FailingProvider(MemoryProvider):
    name = "failing"

    async def ensure_bank(self) -> None:
        return None

    async def retain(self, **kwargs):
        raise HindsightError("hindsight is down")

    async def recall(self, **kwargs):
        raise HindsightError("hindsight is down")

    async def reflect(self, **kwargs):
        raise HindsightError("hindsight is down")

    async def list_memories(self, **kwargs):
        raise HindsightError("hindsight is down")

    async def health(self) -> str:
        return "unavailable"


@pytest.fixture
def demo_service() -> HindsightService:
    return HindsightService(DemoMemoryProvider())


async def test_retain_then_recall(demo_service: HindsightService):
    retained = await demo_service.retain(
        customer_id=1,
        organization_id=1,
        content=(
            "Support interaction with Arjun Technologies. "
            "Arjun Technologies runs PostgreSQL 16 on AWS RDS. "
            "Their connection limit is 100 connections."
        ),
        context="customer support interaction",
    )
    assert retained.retained is True
    assert retained.provider == "demo"
    assert retained.document_id

    outcome = await demo_service.recall(
        customer_id=1, organization_id=1, query="Which database does Arjun Technologies use?",
        limit=5,
    )
    assert outcome.memories
    joined = " ".join(memory.content for memory in outcome.memories).lower()
    assert "postgresql" in joined
    assert all(memory.customer_id == 1 for memory in outcome.memories)


async def test_recall_is_scoped_to_one_customer(demo_service: HindsightService):
    await demo_service.retain(
        customer_id=1,
        organization_id=1,
        content="Arjun Technologies runs PostgreSQL 16 on AWS RDS with a limit of 100.",
    )
    other = await demo_service.recall(
        customer_id=2, organization_id=1, query="PostgreSQL database", limit=5
    )
    assert other.memories == []


async def test_reflect_returns_answer_and_sources(demo_service: HindsightService):
    await demo_service.retain(
        customer_id=3,
        organization_id=1,
        content="Nova Systems uses SAML SSO with Okta and provisions users automatically.",
    )
    outcome = await demo_service.reflect(
        customer_id=3, organization_id=1, query="What do we know about their identity setup?"
    )
    assert outcome.provider == "demo"
    assert "Demo memory provider is active" in outcome.answer


async def test_provider_errors_are_surfaced_as_hindsight_error():
    service = HindsightService(FailingProvider())
    with pytest.raises(HindsightError):
        await service.recall(customer_id=1, organization_id=1, query="anything")
    with pytest.raises(HindsightError):
        await service.retain(customer_id=1, organization_id=1, content="anything durable")


async def test_count_memories_is_bounded(demo_service: HindsightService):
    for index in range(5):
        await demo_service.retain(
            customer_id=4,
            organization_id=1,
            content=f"Vertex Cloud runs service instance number {index} in region eu-west-1.",
        )
    summary = await demo_service.count_memories(4)
    assert summary["count"] >= 1
    assert summary["capped"] is False


def test_memory_record_defaults_are_safe():
    record = MemoryRecord(id="1", content="x", type="world")
    assert record.source == "hindsight"
    assert record.tags == []
    assert record.customer_id is None
