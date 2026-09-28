"""Domain enumerations stored as VARCHAR values in MySQL."""

from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    agent = "agent"
    viewer = "viewer"


class TicketPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class TicketStatus(str, enum.Enum):
    open = "open"
    investigating = "investigating"
    waiting = "waiting"
    resolved = "resolved"
    escalated = "escalated"


class CustomerStatus(str, enum.Enum):
    active = "active"
    prospect = "prospect"
    churned = "churned"
    paused = "paused"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"
    tool = "tool"


class MemoryOperation(str, enum.Enum):
    retain = "retain"
    recall = "recall"
    reflect = "reflect"


class AgentRunStatus(str, enum.Enum):
    success = "success"
    failed = "failed"
    error = "error"
