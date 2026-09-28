"""Groq LLM integration (chat completions + tool calling).

The frontend never talks to Groq directly. This service is the only place
that talks to the model, and it exposes a provider abstraction so the backend
can boot without credentials in development:

* ``GroqProvider``    - real Groq API (OpenAI compatible chat completions).
* ``DemoLLMProvider`` - clearly labelled deterministic fallback.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from app.core.config import settings
from app.core.errors import LLMError, LLMNotConfiguredError
from app.core.logging import get_logger

logger = get_logger(__name__)

Message = Dict[str, Any]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    content: Optional[str]
    model: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    demo_mode: bool = False

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class LLMProvider(ABC):
    name: str = "abstract"
    model: str = ""

    @abstractmethod
    async def complete(
        self,
        *,
        messages: Sequence[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
    ) -> LLMResponse: ...

    async def health(self) -> str:
        return "configured"


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(self, *, api_key: str, model: str, timeout: float, max_retries: int) -> None:
        from groq import AsyncGroq

        self.model = model
        self._max_retries = max(0, max_retries)
        self._client = AsyncGroq(api_key=api_key, timeout=timeout, max_retries=0)

    async def complete(
        self,
        *,
        messages: Sequence[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        started = time.perf_counter()
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        last_error: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            try:
                completion = await self._client.chat.completions.create(**payload)
                break
            except asyncio.TimeoutError as exc:
                last_error = exc
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if not _is_retryable(exc) or attempt == self._max_retries:
                    logger.error("groq.request_failed", extra={"error": str(exc)})
                    raise LLMError(f"Groq request failed: {exc}") from exc
            await asyncio.sleep(min(2 ** attempt, 8) * (0.5 + random.random() / 2))
        else:  # pragma: no cover - loop always breaks or raises
            raise LLMError(f"Groq request failed: {last_error}")

        latency_ms = int((time.perf_counter() - started) * 1000)
        choice = completion.choices[0]
        message = choice.message
        tool_calls = []
        for call in getattr(message, "tool_calls", None) or []:
            tool_calls.append(
                ToolCall(
                    id=call.id,
                    name=call.function.name,
                    arguments=_safe_json(call.function.arguments),
                )
            )
        usage = getattr(completion, "usage", None)
        return LLMResponse(
            content=message.content,
            model=self.model,
            tool_calls=tool_calls,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            latency_ms=latency_ms,
        )


class DemoLLMProvider(LLMProvider):
    """Deterministic stand-in used only when GROQ_API_KEY is not configured.

    It never pretends to be a real model: the response is explicitly labelled
    and the caller receives ``demo_mode=True``.
    """

    name = "demo"

    def __init__(self) -> None:
        self.model = "demo-provider"

    async def complete(
        self,
        *,
        messages: Sequence[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        await asyncio.sleep(0)
        last_user = ""
        for message in reversed(list(messages)):
            if message.get("role") == "user":
                last_user = str(message.get("content", ""))
                break
        content = (
            "[DEMO MODE] No Groq API key is configured, so this reply was generated "
            "locally without an LLM. The memory pipeline above is real. "
            f"Customer message: {last_user[:200]}"
        )
        return LLMResponse(content=content, model=self.model, demo_mode=True)


def _safe_json(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _is_retryable(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    if any(token in name for token in ("timeout", "ratelimit", "internalserver", "apistatus")):
        return True
    text = str(exc).lower()
    return any(token in text for token in ("rate limit", "timeout", "temporarily", "503", "429"))


class LLMService:
    def __init__(self, provider: Optional[LLMProvider] = None) -> None:
        self._provider = provider or build_llm_provider()

    @property
    def provider_name(self) -> str:
        return self._provider.name

    @property
    def model(self) -> str:
        return self._provider.model

    @property
    def is_demo(self) -> bool:
        return self._provider.name == "demo"

    async def complete(
        self,
        *,
        messages: Sequence[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        return await self._provider.complete(messages=messages, tools=tools, temperature=temperature)

    async def health(self) -> str:
        return await self._provider.health()


def build_llm_provider() -> LLMProvider:
    if settings.groq_configured:
        return GroqProvider(
            api_key=settings.groq_api_key or "",
            model=settings.groq_model,
            timeout=settings.groq_timeout_seconds,
            max_retries=settings.groq_max_retries,
        )
    if settings.is_production:
        raise LLMNotConfiguredError()
    logger.warning("groq.using_demo_provider")
    return DemoLLMProvider()


_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    global _service
    if _service is None:
        _service = LLMService()
    return _service


def reset_llm_service() -> None:
    global _service
    _service = None
