"""Audit/observability log of Hindsight memory operations.

This table is *not* a memory store. It only records that a retain/recall/
reflect call happened so the UI can show memory activity.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import MemoryOperation

if TYPE_CHECKING:  # pragma: no cover
    from app.models.conversation import Conversation
    from app.models.customer import Customer


def _values(enum_cls) -> list[str]:
    return [member.value for member in enum_cls]


class MemoryEvent(IdMixin, TimestampMixin, Base):
    __tablename__ = "memory_events"

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    operation: Mapped[str] = mapped_column(
        SAEnum(MemoryOperation, native_enum=False, length=20, values_callable=_values),
        nullable=False,
    )
    query: Mapped[str | None] = mapped_column(Text, nullable=True)
    memory_count: Mapped[int] = mapped_column(nullable=False, default=0)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)

    customer: Mapped["Customer"] = relationship(back_populates="memory_events")
    conversation: Mapped["Conversation | None"] = relationship(
        back_populates="memory_events"
    )

    __table_args__ = (
        Index("ix_memory_events_customer_created", "customer_id", "created_at"),
    )
