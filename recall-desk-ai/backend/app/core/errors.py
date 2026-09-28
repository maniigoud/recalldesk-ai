"""Application level exceptions with stable API error codes."""

from __future__ import annotations

from typing import Any, Dict, Optional


class AppError(Exception):
    status_code = 500
    code = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        status_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details or {}

    def to_payload(self) -> Dict[str, Any]:
        error: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            error["details"] = self.details
        return {"error": error}


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class CustomerNotFoundError(NotFoundError):
    code = "CUSTOMER_NOT_FOUND"

    def __init__(self, customer_id: int | None = None, message: str | None = None) -> None:
        super().__init__(message or f"Customer {customer_id} was not found.")


class TicketNotFoundError(NotFoundError):
    code = "TICKET_NOT_FOUND"

    def __init__(self, ticket_id: int | None = None, message: str | None = None) -> None:
        super().__init__(message or f"Ticket {ticket_id} was not found.")


class ConversationNotFoundError(NotFoundError):
    code = "CONVERSATION_NOT_FOUND"

    def __init__(self, conversation_id: int | None = None, message: str | None = None) -> None:
        super().__init__(message or f"Conversation {conversation_id} was not found.")


class OrganizationNotFoundError(NotFoundError):
    code = "ORGANIZATION_NOT_FOUND"


class ValidationError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"


class AuthenticationError(AppError):
    status_code = 401
    code = "AUTHENTICATION_FAILED"

    def __init__(self, message: str = "Invalid credentials.") -> None:
        super().__init__(message)


class AuthorizationError(AppError):
    status_code = 403
    code = "FORBIDDEN"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "SERVICE_UNAVAILABLE"


class LLMError(ServiceUnavailableError):
    code = "LLM_ERROR"


class HindsightError(ServiceUnavailableError):
    code = "HINDSIGHT_ERROR"


class LLMNotConfiguredError(ServiceUnavailableError):
    code = "LLM_NOT_CONFIGURED"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or "GROQ_API_KEY is not configured. The AI support endpoints require a Groq API key."
        )


class HindsightNotConfiguredError(ServiceUnavailableError):
    code = "HINDSIGHT_NOT_CONFIGURED"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or "HINDSIGHT_API_URL and HINDSIGHT_API_KEY are not configured. "
            "Persistent customer memory is unavailable."
        )
