"""Support ticket."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import Enum as SAEnum
from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import TicketPriority, TicketStatus

if TYPE_CHECKING:  # pragma: no cover
    from app.models.conversation import Conversation
    from app.models.customer import Customer
    from app.models.resolution import Resolution
    from app.models.user import User


def _values(enum_cls) -> list[str]:
    return [member.value for member in enum_cls]


class Ticket(IdMixin, TimestampMixin, Base):
    __tablename__ = "tickets"

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(
        SAEnum(TicketPriority, native_enum=False, length=20, values_callable=_values),
        nullable=False,
        default=TicketPriority.medium.value,
    )
    status: Mapped[str] = mapped_column(
        SAEnum(TicketStatus, native_enum=False, length=20, values_callable=_values),
        nullable=False,
        default=TicketStatus.open.value,
        index=True,
    )
    assigned_to: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    customer: Mapped["Customer"] = relationship(back_populates="tickets")
    assignee: Mapped["User | None"] = relationship(back_populates="assigned_tickets")
    conversations: Mapped[List["Conversation"]] = relationship(back_populates="ticket")
    resolutions: Mapped[List["Resolution"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_tickets_status_priority", "status", "priority"),
        Index("ix_tickets_created_at", "created_at"),
    )
