"""Outcome of a resolved ticket."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.ticket import Ticket


class Resolution(IdMixin, TimestampMixin, Base):
    __tablename__ = "resolutions"

    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    solution: Mapped[str] = mapped_column(Text, nullable=False)
    successful: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    ticket: Mapped["Ticket"] = relationship(back_populates="resolutions")
