"""Tool registry used by the AI agent.

The LLM never touches the database. It emits a tool call, the registry
validates the arguments, checks the caller's role, calls the service layer and
returns a JSON string result. Failures are returned to the model as structured
errors instead of raising.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Sequence

from pydantic import ValidationError

from app.core.logging import get_logger

logger = get_logger(__name__)

Handler = Callable[..., Awaitable[Any]]


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Handler
    roles: Sequence[str] = ("admin", "agent", "viewer")
    write: bool = False

    def to_openai_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolCallRejected(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ToolRegistry:
    def __init__(self, role: str = "agent") -> None:
        self.role = role
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        self._tools[definition.name] = definition

    def register_all(self, definitions: Sequence[ToolDefinition]) -> None:
        for definition in definitions:
            self.register(definition)

    @property
    def names(self) -> List[str]:
        return list(self._tools)

    def definitions(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def schemas(self) -> List[Dict[str, Any]]:
        return [tool.to_openai_schema() for tool in self._tools.values()]

    async def execute(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            return {"ok": False, "error": "UNKNOWN_TOOL", "message": f"Unknown tool '{name}'."}
        if self.role not in tool.roles:
            logger.warning(
                "tool.permission_denied", extra={"tool": name, "role": self.role}
            )
            return {
                "ok": False,
                "error": "PERMISSION_DENIED",
                "message": f"Role '{self.role}' is not allowed to use '{name}'.",
            }
        try:
            result = await tool.handler(**(arguments or {}))
        except TypeError as exc:
            return {"ok": False, "error": "INVALID_ARGUMENTS", "message": str(exc)}
        except ToolCallRejected as exc:
            return {"ok": False, "error": exc.code, "message": exc.message}
        except ValidationError as exc:
            return {
                "ok": False,
                "error": "INVALID_ARGUMENTS",
                "message": exc.errors()[0].get("msg", "invalid arguments"),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("tool.execution_failed", extra={"tool": name, "error": str(exc)})
            return {"ok": False, "error": "TOOL_ERROR", "message": str(exc)}
        return {"ok": True, "result": result}


def dumps(payload: Any) -> str:
    return json.dumps(payload, default=str)
