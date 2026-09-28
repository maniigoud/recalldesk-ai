"""Customer account tracked by the support team."""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import CustomerStatus

if TYPE_CHECKING:  # pragma: no cover
    from app.models.conversation import Conversation
    from app.models.memory_event import MemoryEvent
    from app.models.organization import Organization
    from app.models.ticket import Ticket


def _values(enum_cls) -> list[str]:
    return [member.value for member in enum_cls]


class Customer(IdMixin, TimestampMixin, Base):
    __tablename__ = "customers"

    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(
        SAEnum(CustomerStatus, native_enum=False, length=20, values_callable=_values),
        nullable=False,
        default=CustomerStatus.active.value,
    )

    organization: Mapped["Organization"] = relationship(back_populates="customers")
    tickets: Mapped[List["Ticket"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )
    conversations: Mapped[List["Conversation"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )
    memory_events: Mapped[List["MemoryEvent"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Emails are unique per organization, not globally.
        UniqueConstraint("organization_id", "email", name="uq_customers_org_email"),
    )
