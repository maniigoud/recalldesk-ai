"""A support conversation session.

A conversation is ephemeral session state. It never replaces persistent
customer memory, which lives in Hindsight.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.customer import Customer
    from app.models.memory_event import MemoryEvent
    from app.models.message import Message
    from app.models.ticket import Ticket


class Conversation(IdMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticket_id: Mapped[int | None] = mapped_column(
        ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    customer: Mapped["Customer"] = relationship(back_populates="conversations")
    ticket: Mapped["Ticket | None"] = relationship(back_populates="conversations")
    messages: Mapped[List["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.id",
    )
    agent_runs: Mapped[List["AgentRun"]] = relationship(  # noqa: F821
        back_populates="conversation", cascade="all, delete-orphan"
    )
    memory_events: Mapped[List["MemoryEvent"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_conversations_session_id", "session_id"),)
