"""The support agent pipeline.

Flow (see docs/architecture.md):

    user message
      -> store in MySQL
      -> Hindsight recall (customer scoped)
      -> MySQL customer/ticket context
      -> build agent context
      -> Groq with tool calling
      -> store assistant message
      -> decide what is worth remembering
      -> Hindsight retain
      -> record memory event + agent run
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import HindsightError, LLMError
from app.core.logging import get_logger
from app.models.enums import AgentRunStatus, MemoryOperation, MessageRole
from app.models.memory_event import MemoryEvent
from app.models.agent_run import AgentRun
from app.schemas.conversation import ConversationCreate
from app.schemas.support import SupportChatResponse, ToolUsage
from app.services.conversation_service import ConversationService
from app.services.customer_service import CustomerService
from app.services.hindsight_service import HindsightService
from app.services.knowledge_base_service import knowledge_base
from app.services.llm_service import LLMService, Message
from app.services.ticket_service import TicketService
from app.tools.customer_tools import build_customer_tools
from app.tools.knowledge_tools import build_knowledge_tools
from app.tools.memory_tools import build_memory_tools
from app.tools.registry import ToolRegistry
from app.tools.ticket_tools import build_ticket_tools

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are the RecallDesk support agent, an AI assistant for a customer support team.

Your job is to help one customer with a technical or account problem, and to remember what
matters about them for future conversations.

CONTEXT YOU ARE GIVEN
- CURRENT CUSTOMER RECORD: live data from the support database (authoritative right now).
- CUSTOMER MEMORY: notes retained from earlier support conversations. These are historical
  and may be out of date.
- KNOWLEDGE BASE: RecallDesk's own product documentation.
- TOOLS: live lookups and ticket actions. Use them instead of guessing.

HOW TO USE MEMORY
- Use recalled memory naturally: "This looks similar to the timeout your team hit in March."
- Never mention that you have a memory system, a database of notes, or a tool called
  Hindsight. Just use what you know.
- Only state a remembered fact if it actually appears in the context you were given. If it is
  not there, you do not know it.
- If the live customer record contradicts a memory, trust the live record and say you are
  checking the current configuration.
- Prefer a previously successful fix when it applies to the same problem, but say clearly that
  the circumstances may have changed.

STYLE
- Be concise and practical. Short paragraphs, numbered steps for procedures.
- Match the technical depth the customer has shown. If they write like an engineer, answer
  like one; if not, explain plainly without jargon.
- Ask for the specific missing detail instead of guessing.
- If you are uncertain, say so and describe what would confirm it.
- Do not invent error messages, log lines, ticket numbers, dates or past incidents.

ESCALATION
- Escalate and say so plainly when there is a data loss risk, a security concern, a billing
  dispute, a legal or contractual question, or a blast radius you cannot assess.
- Never promise a fix, an SLA, or a refund.

LEARNING
- Durable details (stack, infrastructure, configuration, preferences, what fixed a past
  incident) are extracted and remembered automatically. You do not need to ask the customer to
  "tell me everything" - the pipeline handles it.
"""

MEMORY_EXTRACTION_PROMPT = """You extract durable support memory from a customer conversation.

A durable memory is information that will still be useful in a FUTURE support conversation:
- technology stack, infrastructure, versions, deployment details, configuration values
- product/account context (plan, seats, integrations, environments)
- communication preferences (technical depth, channel, language, timing)
- incidents: what broke, when, symptoms, root cause
- resolutions: what actually fixed it, and whether the fix worked
- recurring problems, related systems and dependencies

NOT durable: greetings, thanks, acknowledgements, restating the question, generic advice,
one-off status chatter, anything the customer only just asked for with no new information.

Memory types:
- "fact": objective, stable information about the customer or their systems
- "preference": how they want to be communicated with, or what they consistently choose
- "experience": an incident or troubleshooting episode that happened
- "resolution": a fix that worked (or demonstrably did not work)

Rules:
- Each memory must be a single self-contained sentence that makes sense without the conversation.
- Never invent information. If the conversation does not state it, do not write it.
- Prefer 0 memories over weak ones. If nothing durable was learned, return an empty list.
- Reference the customer by their company/person name as used in the conversation.

Return ONLY valid JSON, no prose, no code fences:
{"memories": [{"type": "fact", "content": "..."}]}
"""

_DURABLE_KEYWORDS = (
    "uses", "using", "running", "deployed", "deploying", "version", "configured",
    "configuration", "limit", "timeout", "database", "postgres", "mysql", "redis",
    "kubernetes", "docker", "aws", "gcp", "azure", "rds", "api", "endpoint",
    "prefers", "prefer", "always", "never", "must", "requires", "fixed", "resolved",
    "worked", "didn't work", "did not work", "caused by", "root cause", "logs show",
    "connection", "pool", "migration", "environment", "plan", "seats", "slack",
    "email", "on-call", "escalate", "window", "region", "tenant",
)

_PLEASANTRY = {
    "hello", "hi", "hey", "thanks", "thank you", "ok", "okay", "sure", "yes", "no",
    "got it", "understood", "cheers", "bye", "good morning", "good afternoon",
}

MEMORY_TYPE_MAP = {
    "fact": "fact",
    "preference": "preference",
    "experience": "experience",
    "resolution": "resolution",
}


def is_durable(text: str) -> bool:
    """Heuristic durability check used when no LLM is available."""
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) < 25 or len(cleaned) > 600:
        return False
    lowered = cleaned.lower()
    if lowered.strip(".! ") in _PLEASANTRY:
        return False
    if any(lowered.startswith(f"{p} ") for p in _PLEASANTRY) and len(lowered) < 60:
        return False
    has_number = bool(re.search(r"\d", cleaned))
    has_keyword = any(keyword in lowered for keyword in _DURABLE_KEYWORDS)
    return has_number or has_keyword


class AgentService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        organization_id: int,
        user_id: int,
        role: str,
        conversations: ConversationService,
        customers: CustomerService,
        tickets: TicketService,
        memory: HindsightService,
        llm: LLMService,
    ) -> None:
        self.session = session
        self.organization_id = organization_id
        self.user_id = user_id
        self.role = role
        self.conversations = conversations
        self.customers = customers
        self.tickets = tickets
        self.memory = memory
        self.llm = llm
        self._registry = self._build_registry()

    def _build_registry(self) -> ToolRegistry:
        registry = ToolRegistry(role=self.role)
        registry.register_all(build_customer_tools(self.customers, self.tickets))
        registry.register_all(build_ticket_tools(self.tickets))
        registry.register_all(build_knowledge_tools())
        registry.register_all(
            build_memory_tools(self.memory, self.organization_id)
        )
        return registry

    # ------------------------------------------------------------------ run

    async def run_chat(
        self,
        *,
        customer_id: int,
        message: str,
        conversation_id: Optional[int] = None,
        ticket_id: Optional[int] = None,
        persist: bool = True,
    ) -> SupportChatResponse:
        started = time.perf_counter()
        warnings: List[str] = []

        customer = await self.customers.get(customer_id)

        if conversation_id is not None:
            conversation = await self.conversations.get(conversation_id)
            if conversation.customer_id != customer.id:
                from app.core.errors import ValidationError

                raise ValidationError(
                    "The conversation does not belong to this customer."
                )
        else:
            if not persist:
                from app.core.errors import ValidationError

                raise ValidationError(
                    "conversation_id is required when persist is false."
                )
            conversation = await self.conversations.create(
                customer.id, ConversationCreate(ticket_id=ticket_id)
            )

        if persist:
            await self.conversations.add_message(conversation.id, message, MessageRole.user)

        # 5. Recall relevant memories (Hindsight RECALL).
        try:
            recall = await self.memory.recall(
                customer_id=customer.id,
                organization_id=self.organization_id,
                query=message,
                limit=6,
            )
            memories = recall.memories
        except HindsightError as exc:
            logger.warning(
                "agent.recall_failed", extra={"customer_id": customer.id, "error": str(exc)}
            )
            memories = []
            warnings.append(f"Memory recall unavailable: {exc.message}")

        await self._record_memory_event(
            customer_id=customer.id,
            conversation_id=conversation.id if persist else None,
            operation=MemoryOperation.recall,
            query=message,
            count=len(memories),
        )

        # 6-7. Database context + prompt assembly.
        tickets = await self.tickets.history(customer.id, limit=5)
        recent_messages = (
            await self.conversations.recent_messages(conversation.id, limit=10)
            if persist
            else []
        )
        kb_documents = knowledge_base.search(message, limit=2)

        context = self._build_context(
            customer=customer,
            tickets=tickets,
            memories=memories,
            kb_documents=kb_documents,
        )

        # 8-10. LLM + tool loop.
        tools_used: List[ToolUsage] = []
        answer, tokens, demo_mode = await self._run_llm_loop(
            context=context,
            user_message=message,
            recent_messages=recent_messages,
            tools_used=tools_used,
        )

        # 11. Persist the assistant reply.
        if persist:
            await self.conversations.add_message(
                conversation.id, answer, MessageRole.assistant
            )

        # 12-13. Decide what is worth remembering, then RETAIN.
        retained_summary: Optional[str] = None
        memory_retained = False
        if persist:
            retained = await self._extract_and_retain(
                customer=customer,
                conversation_id=conversation.id,
                user_message=message,
                answer=answer,
            )
            memory_retained = bool(retained)
            if retained:
                retained_summary = "; ".join(item["content"] for item in retained)
            await self._record_memory_event(
                customer_id=customer.id,
                conversation_id=conversation.id,
                operation=MemoryOperation.retain,
                query=retained_summary or "no durable memory extracted",
                count=len(retained or []),
            )

        latency_ms = int((time.perf_counter() - started) * 1000)
        agent_run = AgentRun(
            conversation_id=conversation.id,
            model=self.llm.model,
            latency_ms=latency_ms,
            tokens=tokens,
            status=AgentRunStatus.success.value,
        )
        self.session.add(agent_run)
        await self.session.flush()
        await self.session.refresh(agent_run)

        if self.memory.is_demo:
            warnings.append(
                "Hindsight credentials are not configured: running with the labelled demo "
                "memory provider."
            )
        if self.llm.is_demo:
            warnings.append(
                "GROQ_API_KEY is not configured: running with the labelled demo LLM provider."
            )

        logger.info(
            "agent.run",
            extra={
                "conversation_id": conversation.id,
                "customer_id": customer.id,
                "model": self.llm.model,
                "tools_used": [tool.name for tool in tools_used],
                "memories_recalled": len(memories),
                "memory_retained": memory_retained,
                "latency_ms": latency_ms,
                "tokens": tokens,
            },
        )

        return SupportChatResponse(
            conversation_id=conversation.id,
            session_id=conversation.session_id,
            message=answer,
            memories_recalled=len(memories),
            memory_retained=memory_retained,
            memory_provider=self.memory.provider_name,
            llm_provider=self.llm.provider_name,
            model=self.llm.model,
            tools_used=[tool.name for tool in tools_used],
            tool_details=tools_used,
            recalled_memories=memories,
            retained_summary=retained_summary,
            demo_mode=demo_mode or self.memory.is_demo or self.llm.is_demo,
            warnings=warnings,
            agent_run_id=agent_run.id,
            latency_ms=latency_ms,
            tokens=tokens,
        )

    # -------------------------------------------------------------- context

    def _build_context(
        self,
        *,
        customer,
        tickets: Sequence[Any],
        memories: Sequence[Any],
        kb_documents: Sequence[Dict[str, Any]],
    ) -> str:
        parts: List[str] = ["<current_customer_record>"]
        parts.append(f"name: {customer.name}")
        parts.append(f"company: {customer.company or 'unknown'}")
        parts.append(f"email: {customer.email}")
        parts.append(f"status: {customer.status}")
        if tickets:
            parts.append("recent tickets:")
            for ticket in tickets:
                parts.append(
                    f"- #{ticket.id} [{ticket.status}/{ticket.priority}] {ticket.title}"
                )
        else:
            parts.append("recent tickets: none")
        parts.append("</current_customer_record>")

        if memories:
            parts.append("<customer_memory>")
            for memory in memories:
                stamp = memory.occurred_start.isoformat() if memory.occurred_start else "unknown date"
                parts.append(f"- ({memory.type}, {stamp}) {memory.content}")
            parts.append("</customer_memory>")
        else:
            parts.append(
                "<customer_memory>No relevant memory was recalled for this question. "
                "Do not assume you know anything about this customer's history.</customer_memory>"
            )

        if kb_documents:
            parts.append("<knowledge_base>")
            for document in kb_documents:
                parts.append(f"### {document['title']} ({document['category']})")
                parts.append(str(document["content"])[:900])
            parts.append("</knowledge_base>")

        return "\n".join(parts)

    async def _run_llm_loop(
        self,
        *,
        context: str,
        user_message: str,
        recent_messages: Sequence[Any],
        tools_used: List[ToolUsage],
    ) -> Tuple[str, int, bool]:
        messages: List[Message] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for message in recent_messages:
            if message.role == MessageRole.user.value:
                messages.append({"role": "user", "content": message.content})
            elif message.role == MessageRole.assistant.value:
                messages.append({"role": "assistant", "content": message.content})
        messages.append(
            {
                "role": "user",
                "content": f"{context}\n\n<customer_message>\n{user_message}\n</customer_message>",
            }
        )

        tools = self._registry.schemas()
        total_tokens = 0
        demo_mode = False

        for iteration in range(settings.agent_max_tool_iterations):
            try:
                response = await self.llm.complete(messages=messages, tools=tools)
            except LLMError:
                raise
            total_tokens += response.total_tokens
            demo_mode = demo_mode or response.demo_mode

            if not response.tool_calls:
                return (
                    (response.content or "").strip()
                    or "I was unable to produce an answer for that request.",
                    total_tokens,
                    demo_mode,
                )

            messages.append(
                {
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments),
                            },
                        }
                        for call in response.tool_calls
                    ],
                }
            )

            for call in response.tool_calls:
                outcome = await self._registry.execute(call.name, call.arguments)
                tools_used.append(
                    ToolUsage(name=call.name, arguments_summary=_summarize(call.arguments))
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(outcome, default=str)[:6000],
                    }
                )

            if iteration == settings.agent_max_tool_iterations - 1:
                messages.append(
                    {
                        "role": "user",
                        "content": "Answer now using what you have. Do not call more tools.",
                    }
                )

        response = await self.llm.complete(messages=messages, tools=None)
        total_tokens += response.total_tokens
        demo_mode = demo_mode or response.demo_mode
        return (
            (response.content or "").strip()
            or "I was unable to produce an answer for that request.",
            total_tokens,
            demo_mode,
        )

    # --------------------------------------------------------------- memory

    async def _extract_and_retain(
        self, *, customer, conversation_id: int, user_message: str, answer: str
    ) -> List[Dict[str, str]]:
        transcript = (
            f"Customer message: {user_message}\n"
            f"Support agent reply: {answer}"
        )
        extracted = await self._extract_memories(transcript, customer)
        if not extracted:
            return []

        bullets = "\n".join(f"- {item['content']}" for item in extracted)
        content = (
            f"Support interaction with {customer.name} "
            f"({customer.company or 'no company'}, customer email {customer.email}).\n"
            f"Durable information learned in this conversation:\n{bullets}"
        )
        try:
            await self.memory.retain(
                customer_id=customer.id,
                organization_id=self.organization_id,
                content=content,
                context="customer support interaction",
                conversation_id=conversation_id,
                timestamp=datetime.now(timezone.utc),
                metadata={"conversation_id": str(conversation_id)},
                entities=[
                    {"text": customer.name, "type": "ORG"},
                    {"text": customer.company or customer.name, "type": "ORG"},
                ],
            )
        except HindsightError as exc:
            logger.warning(
                "agent.retain_failed", extra={"customer_id": customer.id, "error": str(exc)}
            )
            return []
        return extracted

    async def _extract_memories(
        self, transcript: str, customer
    ) -> List[Dict[str, str]]:
        if self.llm.is_demo:
            return [
                {"type": "fact", "content": sentence}
                for sentence in _split_sentences(transcript)
                if is_durable(sentence)
            ][:5]

        messages: List[Message] = [
            {"role": "system", "content": MEMORY_EXTRACTION_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Customer: {customer.name} ({customer.company or 'no company'})\n\n"
                    f"Conversation excerpt:\n{transcript}"
                ),
            },
        ]
        try:
            response = await self.llm.complete(messages=messages, temperature=0.0)
        except LLMError as exc:
            logger.warning("agent.memory_extraction_failed", extra={"error": str(exc)})
            return [
                {"type": "fact", "content": sentence}
                for sentence in _split_sentences(transcript)
                if is_durable(sentence)
            ][:5]

        payload = _parse_json_object(response.content or "")
        raw = payload.get("memories") if isinstance(payload, dict) else None
        if not isinstance(raw, list):
            return []

        results: List[Dict[str, str]] = []
        seen = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content", "")).strip()
            memory_type = MEMORY_TYPE_MAP.get(str(item.get("type", "fact")).lower(), "fact")
            if not content or len(content) < 15 or content.lower() in seen:
                continue
            seen.add(content.lower())
            results.append({"type": memory_type, "content": content[:500]})
            if len(results) >= 8:
                break
        return results

    async def _record_memory_event(
        self,
        *,
        customer_id: int,
        conversation_id: Optional[int],
        operation: MemoryOperation,
        query: Optional[str],
        count: int,
    ) -> None:
        self.session.add(
            MemoryEvent(
                customer_id=customer_id,
                conversation_id=conversation_id,
                operation=operation.value,
                query=(query or "")[:2000] or None,
                memory_count=count,
                provider=self.memory.provider_name,
            )
        )
        await self.session.flush()


def _split_sentences(text: str) -> List[str]:
    cleaned = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [part.strip() for part in parts if part.strip()]


def _parse_json_object(text: str) -> Dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```[a-zA-Z]*\n?", "", candidate)
        candidate = re.sub(r"\n?```$", "", candidate).strip()
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        parsed = json.loads(candidate[start : end + 1])
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _summarize(arguments: Dict[str, Any]) -> str:
    parts = []
    for key, value in list(arguments.items())[:4]:
        text = str(value)
        parts.append(f"{key}={text[:60]}")
    return ", ".join(parts)
