"""Import every model so Alembic autogenerate and the metadata registry see them."""

from app.db.base import Base
from app.models.agent_run import AgentRun
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.enums import (
    AgentRunStatus,
    CustomerStatus,
    MemoryOperation,
    MessageRole,
    TicketPriority,
    TicketStatus,
    UserRole,
)
from app.models.memory_event import MemoryEvent
from app.models.message import Message
from app.models.organization import Organization
from app.models.resolution import Resolution
from app.models.ticket import Ticket
from app.models.user import User

__all__ = [
    "AgentRun",
    "AgentRunStatus",
    "Base",
    "Conversation",
    "Customer",
    "CustomerStatus",
    "MemoryEvent",
    "MemoryOperation",
    "Message",
    "MessageRole",
    "Organization",
    "Resolution",
    "Ticket",
    "TicketPriority",
    "TicketStatus",
    "User",
    "UserRole",
]
