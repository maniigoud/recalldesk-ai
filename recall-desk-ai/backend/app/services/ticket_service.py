"""Ticket service: organization scoped CRUD, filtering and resolution handling."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import asc, delete, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, TicketNotFoundError
from app.core.logging import get_logger
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.enums import TicketStatus
from app.models.resolution import Resolution
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.ticket import (
    ResolutionRead,
    ResolutionUpsert,
    TicketCreate,
    TicketDetail,
    TicketListResponse,
    TicketRead,
    TicketUpdate,
)

logger = get_logger(__name__)

SORTABLE = {
    "created_at": Ticket.created_at,
    "updated_at": Ticket.updated_at,
    "priority": Ticket.priority,
    "status": Ticket.status,
    "title": Ticket.title,
}


class TicketService:
    def __init__(self, session: AsyncSession, organization_id: int) -> None:
        self.session = session
        self.organization_id = organization_id

    async def get(self, ticket_id: int) -> Ticket:
        result = await self.session.execute(
            select(Ticket)
            .join(Customer, Customer.id == Ticket.customer_id)
            .where(Ticket.id == ticket_id, Customer.organization_id == self.organization_id)
        )
        ticket = result.scalar_one_or_none()
        if not ticket:
            raise TicketNotFoundError(ticket_id)
        return ticket

    async def list(
        self,
        *,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        customer_id: Optional[int] = None,
        assigned_to: Optional[int] = None,
        search: Optional[str] = None,
        limit: int = 25,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
    ) -> TicketListResponse:
        conditions = [Customer.organization_id == self.organization_id]
        if status:
            conditions.append(Ticket.status == status)
        if priority:
            conditions.append(Ticket.priority == priority)
        if customer_id:
            conditions.append(Ticket.customer_id == customer_id)
        if assigned_to:
            conditions.append(Ticket.assigned_to == assigned_to)
        if search:
            pattern = f"%{search.lower()}%"
            conditions.append(
                or_(func.lower(Ticket.title).like(pattern), func.lower(Ticket.description).like(pattern))
            )

        total = int(
            (
                await self.session.execute(
                    select(func.count())
                    .select_from(Ticket)
                    .join(Customer, Customer.id == Ticket.customer_id)
                    .where(*conditions)
                )
            ).scalar_one()
        )

        column = SORTABLE.get(sort_by, Ticket.created_at)
        ordering = desc(column) if sort_dir.lower() == "desc" else asc(column)
        result = await self.session.execute(
            select(Ticket)
            .join(Customer, Customer.id == Ticket.customer_id)
            .where(*conditions)
            .order_by(ordering)
            .limit(limit)
            .offset(offset)
        )
        items: List[Ticket] = list(result.scalars().all())
        return TicketListResponse(
            items=[TicketRead.model_validate(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def create(self, payload: TicketCreate) -> Ticket:
        customer = await self.session.execute(
            select(Customer).where(
                Customer.id == payload.customer_id,
                Customer.organization_id == self.organization_id,
            )
        )
        if not customer.scalar_one_or_none():
            raise NotFoundError("Customer was not found.", code="CUSTOMER_NOT_FOUND")

        if payload.assigned_to is not None:
            await self._validate_assignee(payload.assigned_to)

        ticket = Ticket(
            customer_id=payload.customer_id,
            title=payload.title,
            description=payload.description,
            priority=payload.priority.value,
            status=payload.status.value,
            assigned_to=payload.assigned_to,
        )
        if ticket.status == TicketStatus.resolved.value:
            ticket.resolved_at = datetime.now(timezone.utc)
        self.session.add(ticket)
        await self.session.flush()
        await self.session.refresh(ticket)
        logger.info(
            "ticket.created",
            extra={"ticket_id": ticket.id, "customer_id": ticket.customer_id},
        )
        return ticket

    async def update(
        self, ticket_id: int, payload: TicketUpdate, resolution: Optional[ResolutionUpsert] = None
    ) -> Ticket:
        ticket = await self.get(ticket_id)
        data = payload.model_dump(exclude_unset=True)
        if "priority" in data and data["priority"]:
            data["priority"] = data["priority"].value
        if "status" in data and data["status"]:
            data["status"] = data["status"].value
        if "assigned_to" in data and data["assigned_to"] is not None:
            await self._validate_assignee(data["assigned_to"])

        for field, value in data.items():
            setattr(ticket, field, value)

        if ticket.status == TicketStatus.resolved.value and ticket.resolved_at is None:
            ticket.resolved_at = datetime.now(timezone.utc)
        if ticket.status != TicketStatus.resolved.value:
            ticket.resolved_at = None

        if resolution is not None:
            await self._upsert_resolution(ticket, resolution)

        await self.session.flush()
        await self.session.refresh(ticket)
        return ticket

    async def delete(self, ticket_id: int) -> None:
        ticket = await self.get(ticket_id)
        await self.session.execute(delete(Ticket).where(Ticket.id == ticket.id))
        await self.session.flush()
        logger.info("ticket.deleted", extra={"ticket_id": ticket_id})

    async def detail(self, ticket_id: int) -> TicketDetail:
        ticket = await self.get(ticket_id)
        result = await self.session.execute(
            select(Ticket, Customer, User)
            .join(Customer, Customer.id == Ticket.customer_id)
            .outerjoin(User, User.id == Ticket.assigned_to)
            .where(Ticket.id == ticket.id)
        )
        _, customer, assignee = result.one()
        conversation_count = int(
            (
                await self.session.execute(
                    select(func.count(Conversation.id)).where(Conversation.ticket_id == ticket.id)
                )
            ).scalar_one()
        )
        resolutions = await self.session.execute(
            select(Resolution).where(Resolution.ticket_id == ticket.id).order_by(Resolution.id)
        )
        detail = TicketDetail.model_validate(ticket)
        detail.customer_name = customer.name
        detail.customer_email = customer.email
        detail.assignee_name = assignee.name if assignee else None
        detail.conversation_count = conversation_count
        detail.resolutions = [
            ResolutionRead.model_validate(r) for r in resolutions.scalars().all()
        ]
        return detail

    async def history(self, customer_id: int, limit: int = 10) -> List[Ticket]:
        result = await self.session.execute(
            select(Ticket)
            .join(Customer, Customer.id == Ticket.customer_id)
            .where(Customer.organization_id == self.organization_id, Ticket.customer_id == customer_id)
            .order_by(desc(Ticket.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def _validate_assignee(self, user_id: int) -> None:
        user = await self.session.execute(
            select(User).where(User.id == user_id, User.organization_id == self.organization_id)
        )
        if not user.scalar_one_or_none():
            raise NotFoundError("Assigned user was not found.", code="USER_NOT_FOUND")

    async def _upsert_resolution(self, ticket: Ticket, payload: ResolutionUpsert) -> Resolution:
        existing = await self.session.execute(
            select(Resolution).where(Resolution.ticket_id == ticket.id).order_by(Resolution.id.desc())
        )
        resolution = existing.scalars().first()
        if resolution:
            resolution.summary = payload.summary
            resolution.solution = payload.solution
            resolution.successful = payload.successful
        else:
            resolution = Resolution(
                ticket_id=ticket.id,
                summary=payload.summary,
                solution=payload.solution,
                successful=payload.successful,
            )
            self.session.add(resolution)
        await self.session.flush()
        logger.info(
            "ticket.resolution_saved",
            extra={"ticket_id": ticket.id, "successful": payload.successful},
        )
        return resolution
