"""Customer service: organization scoped CRUD plus memory aware detail view."""

from __future__ import annotations

from typing import List, Optional, Sequence

from sqlalchemy import asc, delete, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, CustomerNotFoundError
from app.core.logging import get_logger
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.enums import CustomerStatus, TicketStatus
from app.models.message import Message
from app.models.ticket import Ticket
from app.schemas.customer import (
    CustomerCreate,
    CustomerDetail,
    CustomerListResponse,
    CustomerRead,
    CustomerUpdate,
    RecentTicket,
)
from app.schemas.memory import MemoryRecord
from app.services.hindsight_service import HindsightService, get_hindsight_service

logger = get_logger(__name__)

SORTABLE = {
    "created_at": Customer.created_at,
    "updated_at": Customer.updated_at,
    "name": Customer.name,
    "email": Customer.email,
    "company": Customer.company,
    "status": Customer.status,
}

OPEN_STATUSES = (
    TicketStatus.open.value,
    TicketStatus.investigating.value,
    TicketStatus.waiting.value,
    TicketStatus.escalated.value,
)


class CustomerService:
    def __init__(
        self,
        session: AsyncSession,
        organization_id: int,
        memory: Optional[HindsightService] = None,
    ) -> None:
        self.session = session
        self.organization_id = organization_id
        self.memory = memory or get_hindsight_service()

    async def get(self, customer_id: int) -> Customer:
        customer = await self.session.get(Customer, customer_id)
        if not customer or customer.organization_id != self.organization_id:
            raise CustomerNotFoundError(customer_id)
        return customer

    async def list(
        self,
        *,
        search: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 25,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
    ) -> CustomerListResponse:
        conditions = [Customer.organization_id == self.organization_id]
        if search:
            pattern = f"%{search.lower()}%"
            conditions.append(
                or_(
                    func.lower(Customer.name).like(pattern),
                    func.lower(Customer.email).like(pattern),
                    func.lower(Customer.company).like(pattern),
                )
            )
        if status:
            conditions.append(Customer.status == status)

        total_result = await self.session.execute(
            select(func.count()).select_from(Customer).where(*conditions)
        )
        total = int(total_result.scalar_one())

        column = SORTABLE.get(sort_by, Customer.created_at)
        ordering = desc(column) if sort_dir.lower() == "desc" else asc(column)

        result = await self.session.execute(
            select(Customer).where(*conditions).order_by(ordering).limit(limit).offset(offset)
        )
        items: Sequence[Customer] = result.scalars().all()
        return CustomerListResponse(
            items=[CustomerRead.model_validate(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def create(self, payload: CustomerCreate) -> Customer:
        duplicate = await self.session.execute(
            select(Customer).where(
                Customer.organization_id == self.organization_id,
                Customer.email == payload.email.lower(),
            )
        )
        if duplicate.scalar_one_or_none():
            raise ConflictError(
                "A customer with this email already exists in your organization.",
                code="CUSTOMER_EMAIL_EXISTS",
            )

        customer = Customer(
            organization_id=self.organization_id,
            name=payload.name,
            email=payload.email.lower(),
            company=payload.company,
            status=payload.status or CustomerStatus.active.value,
        )
        self.session.add(customer)
        await self.session.flush()
        await self.session.refresh(customer)
        logger.info("customer.created", extra={"customer_id": customer.id})
        return customer

    async def update(self, customer_id: int, payload: CustomerUpdate) -> Customer:
        customer = await self.get(customer_id)
        data = payload.model_dump(exclude_unset=True)
        if "email" in data and data["email"]:
            data["email"] = str(data["email"]).lower()
            clash = await self.session.execute(
                select(Customer).where(
                    Customer.organization_id == self.organization_id,
                    Customer.email == data["email"],
                    Customer.id != customer.id,
                )
            )
            if clash.scalar_one_or_none():
                raise ConflictError(
                    "A customer with this email already exists in your organization.",
                    code="CUSTOMER_EMAIL_EXISTS",
                )
        for field, value in data.items():
            setattr(customer, field, value)
        await self.session.flush()
        await self.session.refresh(customer)
        return customer

    async def delete(self, customer_id: int) -> None:
        customer = await self.get(customer_id)
        await self.session.execute(delete(Customer).where(Customer.id == customer.id))
        await self.session.flush()
        logger.info("customer.deleted", extra={"customer_id": customer_id})

    async def detail(self, customer_id: int) -> CustomerDetail:
        customer = await self.get(customer_id)

        ticket_counts = await self.session.execute(
            select(Ticket.status, func.count(Ticket.id))
            .where(Ticket.customer_id == customer.id)
            .group_by(Ticket.status)
        )
        by_status = {row[0]: int(row[1]) for row in ticket_counts.all()}
        ticket_count = sum(by_status.values())
        open_count = sum(by_status.get(status, 0) for status in OPEN_STATUSES)
        resolved_count = by_status.get(TicketStatus.resolved.value, 0)

        conversation_count = int(
            (
                await self.session.execute(
                    select(func.count(Conversation.id)).where(
                        Conversation.customer_id == customer.id
                    )
                )
            ).scalar_one()
        )
        message_count = int(
            (
                await self.session.execute(
                    select(func.count(Message.id))
                    .join(Conversation, Conversation.id == Message.conversation_id)
                    .where(Conversation.customer_id == customer.id)
                )
            ).scalar_one()
        )

        recent_tickets_result = await self.session.execute(
            select(Ticket)
            .where(Ticket.customer_id == customer.id)
            .order_by(desc(Ticket.created_at))
            .limit(5)
        )
        recent_tickets = [RecentTicket.model_validate(t) for t in recent_tickets_result.scalars().all()]

        memory_count = 0
        memory_capped = False
        recent_memories: List[MemoryRecord] = []
        try:
            summary = await self.memory.count_memories(customer.id)
            memory_count = summary["count"]
            memory_capped = summary["capped"]
            recall = await self.memory.recall(
                customer_id=customer.id,
                organization_id=self.organization_id,
                query=recent_tickets[0].title if recent_tickets else customer.name,
                limit=5,
            )
            recent_memories = recall.memories
        except Exception as exc:  # noqa: BLE001 - memory must not break CRUD
            logger.warning(
                "customer.memory_unavailable",
                extra={"customer_id": customer.id, "error": str(exc)},
            )

        detail = CustomerDetail.model_validate(customer)
        detail.ticket_count = ticket_count
        detail.open_ticket_count = open_count
        detail.resolved_ticket_count = resolved_count
        detail.conversation_count = conversation_count
        detail.message_count = message_count
        detail.memory_count = memory_count
        detail.memory_provider = self.memory.provider_name
        detail.recent_tickets = recent_tickets
        detail.recent_memories = recent_memories
        detail.memory_count_capped = memory_capped
        return detail
