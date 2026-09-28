"""One AI agent execution against a conversation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import AgentRunStatus

if TYPE_CHECKING:  # pragma: no cover
    from app.models.conversation import Conversation


def _values(enum_cls) -> list[str]:
    return [member.value for member in enum_cls]


class AgentRun(IdMixin, TimestampMixin, Base):
    __tablename__ = "agent_runs"

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        SAEnum(AgentRunStatus, native_enum=False, length=20, values_callable=_values),
        nullable=False,
        default=AgentRunStatus.success.value,
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="agent_runs")
