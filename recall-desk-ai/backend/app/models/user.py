"""Support agent / admin / viewer user."""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import UserRole

if TYPE_CHECKING:  # pragma: no cover
    from app.models.organization import Organization


def _values(enum_cls) -> list[str]:
    return [member.value for member in enum_cls]


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        SAEnum(UserRole, native_enum=False, length=20, values_callable=_values),
        nullable=False,
        default=UserRole.agent.value,
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    organization: Mapped["Organization"] = relationship(back_populates="users")
    assigned_tickets: Mapped[List["Ticket"]] = relationship(  # noqa: F821
        back_populates="assignee"
    )
