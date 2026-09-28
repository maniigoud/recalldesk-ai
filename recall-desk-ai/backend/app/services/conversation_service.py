"""Conversation service.

A conversation is a *session*: it holds the messages exchanged in one sitting.
Starting a new session never touches Hindsight, so customer memory survives.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConversationNotFoundError, NotFoundError
from app.core.logging import get_logger
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.enums import MessageRole
from app.models.message import Message
from app.models.ticket import Ticket
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetail,
    ConversationListResponse,
    ConversationRead,
    MessageRead,
)

logger = get_logger(__name__)


class ConversationService:
    def __init__(self, session: AsyncSession, organization_id: int) -> None:
        self.session = session
        self.organization_id = organization_id

    async def _customer_in_org(self, customer_id: int) -> Customer:
        result = await self.session.execute(
            select(Customer).where(
                Customer.id == customer_id, Customer.organization_id == self.organization_id
            )
        )
        customer = result.scalar_one_or_none()
        if not customer:
            raise NotFoundError("Customer was not found.", code="CUSTOMER_NOT_FOUND")
        return customer

    async def create(
        self, customer_id: int, payload: Optional[ConversationCreate] = None
    ) -> Conversation:
        customer = await self._customer_in_org(customer_id)
        if payload and payload.ticket_id is not None:
            owned = await self.session.execute(
                select(func.count())
                .select_from(Ticket)
                .join(Customer, Customer.id == Ticket.customer_id)
                .where(
                    Ticket.id == payload.ticket_id,
                    Customer.organization_id == self.organization_id,
                )
            )
            if not int(owned.scalar_one()):
                raise NotFoundError("Ticket was not found.", code="TICKET_NOT_FOUND")

        conversation = Conversation(
            customer_id=customer.id,
            ticket_id=payload.ticket_id if payload else None,
            session_id=uuid.uuid4().hex,
        )
        self.session.add(conversation)
        await self.session.flush()
        await self.session.refresh(conversation)
        logger.info(
            "conversation.created",
            extra={
                "conversation_id": conversation.id,
                "customer_id": customer.id,
                "session_id": conversation.session_id,
            },
        )
        return conversation

    async def get(self, conversation_id: int) -> Conversation:
        result = await self.session.execute(
            select(Conversation)
            .join(Customer, Customer.id == Conversation.customer_id)
            .where(
                Conversation.id == conversation_id,
                Customer.organization_id == self.organization_id,
            )
        )
        conversation = result.scalar_one_or_none()
        if not conversation:
            raise ConversationNotFoundError(conversation_id)
        return conversation

    async def list_for_customer(
        self, customer_id: int, *, limit: int = 25, offset: int = 0
    ) -> ConversationListResponse:
        await self._customer_in_org(customer_id)
        total = int(
            (
                await self.session.execute(
                    select(func.count(Conversation.id)).where(
                        Conversation.customer_id == customer_id
                    )
                )
            ).scalar_one()
        )
        result = await self.session.execute(
            select(Conversation)
            .where(Conversation.customer_id == customer_id)
            .order_by(desc(Conversation.created_at))
            .limit(limit)
            .offset(offset)
        )
        conversations = list(result.scalars().all())
        counts = await self.message_counts([c.id for c in conversations])
        items = []
        for conversation in conversations:
            item = ConversationRead.model_validate(conversation)
            item.message_count = counts.get(conversation.id, 0)
            items.append(item)
        return ConversationListResponse(items=items, total=total, limit=limit, offset=offset)

    async def detail(self, conversation_id: int) -> ConversationDetail:
        conversation = await self.get(conversation_id)
        result = await self.session.execute(
            select(Customer).where(Customer.id == conversation.customer_id)
        )
        customer = result.scalar_one()
        messages = await self.list_messages(conversation_id)
        detail = ConversationDetail.model_validate(conversation)
        detail.customer_name = customer.name
        detail.customer_email = customer.email
        detail.messages = messages
        detail.message_count = len(messages)
        return detail

    async def list_messages(self, conversation_id: int) -> List[MessageRead]:
        await self.get(conversation_id)
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.id)
        )
        return [MessageRead.model_validate(message) for message in result.scalars().all()]

    async def add_message(
        self,
        conversation_id: int,
        content: str,
        role: MessageRole = MessageRole.user,
        flush: bool = True,
    ) -> Message:
        await self.get(conversation_id)
        message = Message(
            conversation_id=conversation_id,
            role=role.value,
            content=content,
        )
        self.session.add(message)
        if flush:
            await self.session.flush()
        return message

    async def recent_messages(
        self, conversation_id: int, limit: int = 10
    ) -> List[Message]:
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(desc(Message.id))
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def message_counts(self, conversation_ids: List[int]) -> dict[int, int]:
        if not conversation_ids:
            return {}
        result = await self.session.execute(
            select(Message.conversation_id, func.count(Message.id))
            .where(Message.conversation_id.in_(conversation_ids))
            .group_by(Message.conversation_id)
        )
        return {row[0]: int(row[1]) for row in result.all()}
