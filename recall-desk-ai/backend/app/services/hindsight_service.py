"""Hindsight integration: the single place that talks to Hindsight.

Architecture
------------
``HindsightService`` is the only component the rest of the app uses. It
delegates to a ``MemoryProvider`` implementation:

* ``HindsightCloudProvider`` - the real Hindsight service (Hindsight Cloud or a
  self hosted server), driven by the official ``hindsight_client`` package.
* ``DemoMemoryProvider`` - an in-process, clearly labelled fallback used only
  when credentials are missing and ``APP_ENV`` is not production.

Memory scoping
--------------
A single RecallDesk memory bank (``HINDSIGHT_BANK_ID``) is used for the whole
product. Every retained memory is tagged with
``customer:<customer_id>`` / ``org:<organization_id>`` so recall stays scoped
to one customer, and carries the same identifiers in metadata so results can
be normalized for the frontend.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from app.core.config import settings
from app.core.errors import HindsightError
from app.core.logging import get_logger
from app.schemas.memory import MemoryRecord, MemoryReference

logger = get_logger(__name__)

CUSTOMER_TAG_PREFIX = "customer:"
ORG_TAG_PREFIX = "org:"


def customer_tag(customer_id: int) -> str:
    return f"{CUSTOMER_TAG_PREFIX}{customer_id}"


def org_tag(organization_id: int) -> str:
    return f"{ORG_TAG_PREFIX}{organization_id}"


def customer_id_from(metadata: Optional[Dict[str, Any]], tags: Sequence[str]) -> Optional[int]:
    """Recover the owning customer from metadata, falling back to tags.

    Consolidated `observation` memories do not carry the original metadata, so
    the tags written at retain time are the reliable source.
    """
    if metadata:
        value = metadata.get("customer_id")
        parsed = _maybe_int(value)
        if parsed is not None:
            return parsed
    for tag in tags or ():
        if tag.startswith(CUSTOMER_TAG_PREFIX):
            return _maybe_int(tag[len(CUSTOMER_TAG_PREFIX) :])
    return None


def _parse_dt(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _relevance_from_scores(scores: Any) -> Optional[float]:
    if isinstance(scores, dict):
        for key in ("final", "reranker", "semantic"):
            value = scores.get(key)
            if isinstance(value, (int, float)):
                return float(value)
    return None


@dataclass
class RetainOutcome:
    retained: bool
    provider: str
    document_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RecallOutcome:
    memories: List[MemoryRecord]
    provider: str
    duration_ms: int = 0


@dataclass
class ReflectOutcome:
    answer: str
    memories_used: List[MemoryReference]
    provider: str
    duration_ms: int = 0
    structured_output: Optional[Dict[str, Any]] = None


class MemoryProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    async def ensure_bank(self) -> None: ...

    @abstractmethod
    async def retain(
        self,
        *,
        customer_id: int,
        organization_id: int,
        content: str,
        context: Optional[str],
        document_id: str,
        timestamp: Optional[datetime],
        metadata: Dict[str, str],
        entities: Optional[Sequence[Dict[str, str]]] = None,
    ) -> RetainOutcome: ...

    @abstractmethod
    async def recall(
        self,
        *,
        customer_id: int,
        organization_id: int,
        query: str,
        limit: int,
        types: Optional[List[str]],
        budget: str,
        max_tokens: int,
    ) -> List[MemoryRecord]: ...

    @abstractmethod
    async def reflect(
        self,
        *,
        customer_id: int,
        organization_id: int,
        query: str,
        budget: str,
        max_tokens: Optional[int] = None,
    ) -> ReflectOutcome: ...

    @abstractmethod
    async def list_memories(
        self,
        *,
        customer_id: Optional[int],
        search: Optional[str],
        memory_type: Optional[str],
        limit: int,
        offset: int,
    ) -> Dict[str, Any]: ...

    @abstractmethod
    async def health(self) -> str: ...


class HindsightCloudProvider(MemoryProvider):
    """Real Hindsight provider built on the official ``hindsight_client``."""

    name = "hindsight"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        bank_id: str,
        timeout: float = 60.0,
    ) -> None:
        from hindsight_client import Hindsight

        self._bank_id = bank_id
        self._client = Hindsight(
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            timeout=timeout,
            user_agent="recall-desk-ai-backend",
        )

    @property
    def bank_id(self) -> str:
        return self._bank_id

    async def ensure_bank(self) -> None:
        try:
            await self._client.acreate_bank(
                bank_id=self._bank_id,
                name="RecallDesk AI",
                mission=(
                    "Persistent customer memory for the RecallDesk AI support agent. "
                    "Store customer technology stack, infrastructure, configuration, "
                    "communication preferences, previous incidents, and which "
                    "troubleshooting steps actually resolved them."
                ),
                disposition={"skepticism": 2, "literalism": 3, "empathy": 4},
            )
            logger.info("hindsight.bank_ready", extra={"bank_id": self._bank_id})
        except Exception as exc:  # noqa: BLE001 - bank may already exist
            logger.warning(
                "hindsight.bank_ensure_skipped",
                extra={"bank_id": self._bank_id, "error": str(exc)},
            )

    async def retain(
        self,
        *,
        customer_id: int,
        organization_id: int,
        content: str,
        context: Optional[str],
        document_id: str,
        timestamp: Optional[datetime],
        metadata: Dict[str, str],
        entities: Optional[Sequence[Dict[str, str]]] = None,
    ) -> RetainOutcome:
        tags = [customer_tag(customer_id), org_tag(organization_id), "recall-desk"]
        full_metadata = {
            "customer_id": str(customer_id),
            "organization_id": str(organization_id),
            "source": "recalldesk",
            **metadata,
        }
        try:
            response = await self._client.aretain(
                bank_id=self._bank_id,
                content=content,
                context=context,
                document_id=document_id,
                timestamp=timestamp,
                metadata=full_metadata,
                tags=tags,
                entities=list(entities) if entities else None,
                retain_async=settings.hindsight_retain_async,
            )
        except asyncio.TimeoutError as exc:
            raise HindsightError("Hindsight retain request timed out.") from exc
        except Exception as exc:  # noqa: BLE001
            logger.error("hindsight.retain_failed", extra={"error": str(exc)})
            raise HindsightError(f"Hindsight retain failed: {exc}") from exc

        details: Dict[str, Any] = {}
        if response is not None and hasattr(response, "model_dump"):
            try:
                details = response.model_dump(mode="json")
            except Exception:  # noqa: BLE001
                details = {}
        return RetainOutcome(
            retained=True,
            provider=self.name,
            document_id=document_id,
            details=details,
        )

    async def recall(
        self,
        *,
        customer_id: int,
        organization_id: int,
        query: str,
        limit: int,
        types: Optional[List[str]],
        budget: str,
        max_tokens: int,
    ) -> List[MemoryRecord]:
        try:
            response = await self._client.arecall(
                bank_id=self._bank_id,
                query=query,
                types=types,
                max_tokens=max_tokens,
                budget=budget,
                # Only the customer's own tag. A multi-tag filter is an OR and
                # would return every memory in the organization.
                tags=[customer_tag(customer_id)],
                tags_match="any_strict",
                include_entities=True,
            )
        except asyncio.TimeoutError as exc:
            raise HindsightError("Hindsight recall request timed out.") from exc
        except Exception as exc:  # noqa: BLE001
            logger.error("hindsight.recall_failed", extra={"error": str(exc)})
            raise HindsightError(f"Hindsight recall failed: {exc}") from exc

        records: List[MemoryRecord] = []
        for result in (response.results or []):
            tags = list(result.tags or [])
            owner = customer_id_from(result.metadata, tags)
            if owner is not None and owner != customer_id:
                # Defence in depth: never expose another customer's memory.
                logger.warning(
                    "hindsight.cross_customer_result_dropped",
                    extra={"customer_id": customer_id, "owner": owner},
                )
                continue
            records.append(
                MemoryRecord(
                    id=str(result.id),
                    content=result.text,
                    type=result.type or "world",
                    customer_id=owner,
                    source="hindsight",
                    relevance=_relevance_from_scores(result.scores),
                    created_at=_parse_dt(result.mentioned_at),
                    occurred_start=_parse_dt(result.occurred_start),
                    occurred_end=_parse_dt(result.occurred_end),
                    context=result.context,
                    document_id=result.document_id,
                    tags=tags,
                    metadata=dict(result.metadata or {}),
                    scores=dict(result.scores or {}),
                )
            )
            if len(records) >= limit:
                break
        return records

    async def reflect(
        self,
        *,
        customer_id: int,
        organization_id: int,
        query: str,
        budget: str,
        max_tokens: Optional[int] = None,
    ) -> ReflectOutcome:
        try:
            response = await self._client.areflect(
                bank_id=self._bank_id,
                query=query,
                budget=budget,
                # Same single-tag scoping rule as recall.
                tags=[customer_tag(customer_id)],
                tags_match="any_strict",
                include_facts=True,
                max_tokens=max_tokens or 1500,
            )
        except asyncio.TimeoutError as exc:
            raise HindsightError("Hindsight reflect request timed out.") from exc
        except Exception as exc:  # noqa: BLE001
            logger.error("hindsight.reflect_failed", extra={"error": str(exc)})
            raise HindsightError(f"Hindsight reflect failed: {exc}") from exc

        used: List[MemoryReference] = []
        based_on = getattr(response, "based_on", None)
        for memory in (getattr(based_on, "memories", None) or []):
            used.append(
                MemoryReference(
                    id=str(memory.id), content=memory.text, type=memory.type or "world"
                )
            )
        return ReflectOutcome(
            answer=response.text or "",
            memories_used=used,
            provider=self.name,
            structured_output=getattr(response, "structured_output", None),
        )

    async def list_memories(
        self,
        *,
        customer_id: Optional[int],
        search: Optional[str],
        memory_type: Optional[str],
        limit: int,
        offset: int,
    ) -> Dict[str, Any]:
        try:
            response = await self._client.alist_memories(
                bank_id=self._bank_id,
                type=memory_type,
                search_query=search,
                limit=limit,
                offset=offset,
            )
        except asyncio.TimeoutError as exc:
            raise HindsightError("Hindsight memory listing timed out.") from exc
        except Exception as exc:  # noqa: BLE001
            raise HindsightError(f"Hindsight memory listing failed: {exc}") from exc

        items = response.items or []
        records = []
        for item in items:
            tags = list(item.tags or [])
            owner = customer_id_from(item.metadata, tags)
            if customer_id is not None and owner is not None and owner != customer_id:
                continue
            records.append(
                MemoryRecord(
                    id=str(item.id),
                    content=item.text,
                    # The memory listing endpoint names the category `fact_type`;
                    # recall results name it `type`.
                    type=getattr(item, "fact_type", None) or "world",
                    customer_id=owner,
                    source="hindsight",
                    created_at=_parse_dt(item.mentioned_at),
                    occurred_start=_parse_dt(item.occurred_start),
                    occurred_end=_parse_dt(item.occurred_end),
                    context=item.context,
                    document_id=item.document_id,
                    tags=tags,
                    metadata=dict(item.metadata or {}),
                )
            )
        if customer_id is not None:
            records = [r for r in records if r.customer_id == customer_id]
        return {
            "items": records,
            "total": response.total if response.total is not None else len(records),
            "limit": limit,
            "offset": offset,
        }

    async def health(self) -> str:
        try:
            await asyncio.wait_for(self._client.aget_version(), timeout=25)
        except Exception as exc:  # noqa: BLE001
            logger.warning("hindsight.health_failed", extra={"error": str(exc)})
            return "unavailable"
        return "connected"

    async def aclose(self) -> None:
        try:
            await self._client.aclose()
        except Exception:  # noqa: BLE001
            pass


def _maybe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class DemoMemoryProvider(MemoryProvider):
    """In-process fallback used only when Hindsight is not configured.

    It is intentionally obvious in the API responses (``provider="demo"``) so
    a demo run can never be mistaken for real Hindsight processing.
    """

    name = "demo"

    def __init__(self) -> None:
        self._memories: List[MemoryRecord] = []
        self._lock = asyncio.Lock()

    async def ensure_bank(self) -> None:
        return None

    async def retain(
        self,
        *,
        customer_id: int,
        organization_id: int,
        content: str,
        context: Optional[str],
        document_id: str,
        timestamp: Optional[datetime],
        metadata: Dict[str, str],
        entities: Optional[Sequence[Dict[str, str]]] = None,
    ) -> RetainOutcome:
        async with self._lock:
            for sentence in _split_sentences(content):
                self._memories.append(
                    MemoryRecord(
                        id=uuid.uuid4().hex,
                        content=sentence,
                        type="world",
                        customer_id=customer_id,
                        source="demo",
                        created_at=timestamp or datetime.now(timezone.utc),
                        context=context,
                        document_id=document_id,
                        tags=[customer_tag(customer_id), org_tag(organization_id)],
                        metadata={
                            "customer_id": str(customer_id),
                            "organization_id": str(organization_id),
                            **metadata,
                        },
                    )
                )
        return RetainOutcome(retained=True, provider=self.name, document_id=document_id)

    async def recall(
        self,
        *,
        customer_id: int,
        organization_id: int,
        query: str,
        limit: int,
        types: Optional[List[str]],
        budget: str,
        max_tokens: int,
    ) -> List[MemoryRecord]:
        terms = {token for token in _tokenize(query) if len(token) > 2}
        scored: List[tuple[float, MemoryRecord]] = []
        for memory in self._memories:
            if memory.customer_id != customer_id:
                continue
            if types and memory.type not in types:
                continue
            words = set(_tokenize(memory.content))
            overlap = len(terms & words)
            score = overlap / len(terms) if terms else 0.0
            if score > 0:
                scored.append((score, memory))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        results = []
        for score, memory in scored[:limit]:
            enriched = memory.model_copy(update={"relevance": round(score, 4)})
            results.append(enriched)
        return results

    async def reflect(
        self,
        *,
        customer_id: int,
        organization_id: int,
        query: str,
        budget: str,
        max_tokens: Optional[int] = None,
    ) -> ReflectOutcome:
        memories = await self.recall(
            customer_id=customer_id,
            organization_id=organization_id,
            query=query,
            limit=8,
            types=None,
            budget=budget,
            max_tokens=max_tokens or 1500,
        )
        answer = (
            "Demo memory provider is active (HINDSIGHT_API_KEY is not configured). "
            "No real reflection was performed."
        )
        return ReflectOutcome(
            answer=answer,
            memories_used=[
                MemoryReference(id=m.id, content=m.content, type=m.type) for m in memories
            ],
            provider=self.name,
        )

    async def list_memories(
        self,
        *,
        customer_id: Optional[int],
        search: Optional[str],
        memory_type: Optional[str],
        limit: int,
        offset: int,
    ) -> Dict[str, Any]:
        items = [
            m
            for m in self._memories
            if (customer_id is None or m.customer_id == customer_id)
            and (memory_type is None or m.type == memory_type)
            and (not search or search.lower() in m.content.lower())
        ]
        return {
            "items": items[offset : offset + limit],
            "total": len(items),
            "limit": limit,
            "offset": offset,
        }

    async def health(self) -> str:
        return "unconfigured"


def _tokenize(text: str) -> List[str]:
    return [token.strip(".,!?;:'\"()[]").lower() for token in text.split()]


def _split_sentences(text: str) -> List[str]:
    parts = [part.strip() for part in text.replace("\n", " ").split(".")]
    return [part for part in parts if len(part) > 15][:12]


class HindsightService:
    """Facade over the configured memory provider."""

    def __init__(self, provider: Optional[MemoryProvider] = None) -> None:
        self._provider = provider or build_memory_provider()
        self._bank_ready = False

    @property
    def provider(self) -> MemoryProvider:
        return self._provider

    @property
    def provider_name(self) -> str:
        return self._provider.name

    @property
    def is_demo(self) -> bool:
        return self._provider.name == "demo"

    async def ensure_bank(self, force: bool = False) -> None:
        if self._bank_ready and not force:
            return
        await self._provider.ensure_bank()
        self._bank_ready = True

    async def retain(
        self,
        *,
        customer_id: int,
        organization_id: int,
        content: str,
        context: Optional[str] = "customer support interaction",
        document_id: Optional[str] = None,
        conversation_id: Optional[int] = None,
        timestamp: Optional[datetime] = None,
        metadata: Optional[Dict[str, str]] = None,
        entities: Optional[Sequence[Dict[str, str]]] = None,
    ) -> RetainOutcome:
        await self.ensure_bank()
        document_id = document_id or f"rd-c{customer_id}-{uuid.uuid4().hex[:12]}"
        started = time.perf_counter()
        outcome = await self._provider.retain(
            customer_id=customer_id,
            organization_id=organization_id,
            content=content,
            context=context,
            document_id=document_id,
            timestamp=timestamp,
            metadata=metadata or {},
            entities=entities,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "hindsight.retain",
            extra={
                "customer_id": customer_id,
                "conversation_id": conversation_id,
                "provider": self._provider.name,
                "document_id": document_id,
                "duration_ms": duration_ms,
            },
        )
        return RetainOutcome(
            retained=outcome.retained,
            provider=outcome.provider,
            document_id=document_id,
            details={**outcome.details, "duration_ms": duration_ms},
        )

    async def recall(
        self,
        *,
        customer_id: int,
        organization_id: int,
        query: str,
        limit: int = 8,
        types: Optional[List[str]] = None,
        budget: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> RecallOutcome:
        await self.ensure_bank()
        started = time.perf_counter()
        memories = await self._provider.recall(
            customer_id=customer_id,
            organization_id=organization_id,
            query=query,
            limit=limit,
            types=types,
            budget=budget or settings.hindsight_recall_budget,
            max_tokens=max_tokens or settings.hindsight_recall_max_tokens,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "hindsight.recall",
            extra={
                "customer_id": customer_id,
                "query": query,
                "provider": self._provider.name,
                "memory_count": len(memories),
                "duration_ms": duration_ms,
            },
        )
        return RecallOutcome(
            memories=memories,
            provider=self._provider.name,
            duration_ms=duration_ms,
        )

    async def reflect(
        self,
        *,
        customer_id: int,
        organization_id: int,
        query: str,
        budget: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> ReflectOutcome:
        await self.ensure_bank()
        started = time.perf_counter()
        outcome = await self._provider.reflect(
            customer_id=customer_id,
            organization_id=organization_id,
            query=query,
            budget=budget or "mid",
            max_tokens=max_tokens,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "hindsight.reflect",
            extra={
                "customer_id": customer_id,
                "provider": self._provider.name,
                "duration_ms": duration_ms,
            },
        )
        return ReflectOutcome(
            answer=outcome.answer,
            memories_used=outcome.memories_used,
            provider=outcome.provider,
            duration_ms=duration_ms,
            structured_output=outcome.structured_output,
        )

    async def list_memories(
        self,
        *,
        customer_id: Optional[int] = None,
        search: Optional[str] = None,
        memory_type: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        await self.ensure_bank()
        return await self._provider.list_memories(
            customer_id=customer_id,
            search=search,
            memory_type=memory_type,
            limit=limit,
            offset=offset,
        )

    async def health(self) -> str:
        return await self._provider.health()

    async def count_memories(self, customer_id: int, scan_limit: int = 200) -> Dict[str, int]:
        """Count memories that belong to one customer.

        Hindsight exposes pagination but no tag filter on the memory listing,
        so the app scans a bounded page and filters by the customer tag. When
        the scan window is exhausted the count is reported as a lower bound and
        ``capped`` is set, so the UI never shows a fabricated exact number.
        """
        page = await self.list_memories(
            customer_id=customer_id, limit=scan_limit, offset=0
        )
        count = len(page.get("items", []))
        return {"count": count, "capped": count >= scan_limit}

    async def aclose(self) -> None:
        closer = getattr(self._provider, "aclose", None)
        if closer is not None:
            await closer()


def build_memory_provider() -> MemoryProvider:
    """Pick the real provider when configured, otherwise the labelled demo one."""
    if settings.hindsight_configured:
        return HindsightCloudProvider(
            base_url=settings.hindsight_api_url or "",
            api_key=settings.hindsight_api_key or "",
            bank_id=settings.hindsight_bank_id,
            timeout=settings.hindsight_timeout_seconds,
        )
    if settings.is_production:
        raise HindsightError(
            "Hindsight is not configured. Set HINDSIGHT_API_URL and HINDSIGHT_API_KEY."
        )
    logger.warning("hindsight.using_demo_provider")
    return DemoMemoryProvider()


_service: Optional[HindsightService] = None


def get_hindsight_service() -> HindsightService:
    global _service
    if _service is None:
        _service = HindsightService()
    return _service


def reset_hindsight_service() -> None:
    """Used by tests to inject a provider."""
    global _service
    _service = None
