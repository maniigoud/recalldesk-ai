"""Dashboard and analytics metrics computed from real application data."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.enums import AgentRunStatus, MemoryOperation, TicketStatus
from app.models.memory_event import MemoryEvent
from app.models.organization import Organization
from app.models.ticket import Ticket
from app.schemas.analytics import (
    AgentActivity,
    AnalyticsResponse,
    CategoryCount,
    DashboardResponse,
    MemoryActivityPoint,
)
from app.schemas.ticket import TicketRead

OPEN_STATUSES = (
    TicketStatus.open.value,
    TicketStatus.investigating.value,
    TicketStatus.waiting.value,
    TicketStatus.escalated.value,
)

CATEGORY_KEYWORDS = {
    "timeouts": ("timeout", "timing out", "latency", "slow", "504"),
    "authentication": ("auth", "401", "token", "login", "permission"),
    "billing": ("billing", "invoice", "charge", "refund", "plan", "subscription"),
    "deployments": ("deploy", "release", "rollback", "build", "version"),
    "rate_limiting": ("rate limit", "429", "throttle", "quota"),
    "connectivity": ("connection", "network", "dns", "ssl", "certificate"),
    "data": ("data", "migration", "backup", "restore", "corrupt"),
}


def categorize(title: str, description: str | None) -> str:
    text = f"{title} {description or ''}".lower()
    best, best_hits = "uncategorized", 0
    for category, keywords in CATEGORY_KEYWORDS.items():
        hits = sum(1 for keyword in keywords if keyword in text)
        if hits > best_hits:
            best, best_hits = category, hits
    return best


class AnalyticsService:
    def __init__(
        self,
        session: AsyncSession,
        organization_id: int,
        memory_provider: str = "unknown",
        llm_configured: bool = False,
    ) -> None:
        self.session = session
        self.organization_id = organization_id
        self.memory_provider = memory_provider
        self.llm_configured = llm_configured

    def _org_customers(self):
        return select(Customer.id).where(Customer.organization_id == self.organization_id)

    def _org_tickets(self):
        return (
            select(Ticket.id)
            .join(Customer, Customer.id == Ticket.customer_id)
            .where(Customer.organization_id == self.organization_id)
            .subquery()
        )

    async def _scalar(self, statement) -> int:
        return int((await self.session.execute(statement)).scalar_one() or 0)

    async def dashboard(self, days: int = 14) -> DashboardResponse:
        customer_ids = self._org_customers()

        customer_count = await self._scalar(select(func.count()).select_from(customer_ids.subquery()))
        conversation_count = await self._scalar(
            select(func.count(Conversation.id)).where(
                Conversation.customer_id.in_(customer_ids)
            )
        )

        status_rows = (
            await self.session.execute(
                select(Ticket.status, func.count(Ticket.id))
                .join(Customer, Customer.id == Ticket.customer_id)
                .where(Customer.organization_id == self.organization_id)
                .group_by(Ticket.status)
            )
        ).all()
        by_status = {row[0]: int(row[1]) for row in status_rows}
        open_count = sum(by_status.get(status, 0) for status in OPEN_STATUSES)
        resolved_count = by_status.get(TicketStatus.resolved.value, 0)
        escalated_count = by_status.get(TicketStatus.escalated.value, 0)

        agent_run_count = await self._scalar(
            select(func.count(AgentRun.id))
            .join(Conversation, Conversation.id == AgentRun.conversation_id)
            .where(Conversation.customer_id.in_(customer_ids))
        )

        memory_rows = (
            await self.session.execute(
                select(MemoryEvent.operation, func.count(MemoryEvent.id))
                .where(MemoryEvent.customer_id.in_(customer_ids))
                .group_by(MemoryEvent.operation)
            )
        ).all()
        by_operation = {row[0]: int(row[1]) for row in memory_rows}

        since = datetime.now(timezone.utc) - timedelta(days=days)
        activity_rows = (
            await self.session.execute(
                select(
                    func.date_format(MemoryEvent.created_at, "%Y-%m-%d").label("day"),
                    MemoryEvent.operation,
                    func.count(MemoryEvent.id),
                )
                .where(MemoryEvent.customer_id.in_(customer_ids), MemoryEvent.created_at >= since)
                .group_by("day", MemoryEvent.operation)
            )
        ).all()
        by_day: dict[str, MemoryActivityPoint] = {}
        for day, operation, count in activity_rows:
            point = by_day.setdefault(
                str(day),
                MemoryActivityPoint(date=str(day), retains=0, recalls=0, reflects=0),
            )
            if operation == MemoryOperation.retain.value:
                point.retains = int(count)
            elif operation == MemoryOperation.recall.value:
                point.recalls = int(count)
            elif operation == MemoryOperation.reflect.value:
                point.reflects = int(count)
        activity = [by_day[key] for key in sorted(by_day)]

        recent_tickets = (
            await self.session.execute(
                select(Ticket)
                .join(Customer, Customer.id == Ticket.customer_id)
                .where(Customer.organization_id == self.organization_id)
                .order_by(Ticket.created_at.desc())
                .limit(8)
            )
        ).scalars().all()

        recent_runs = (
            await self.session.execute(
                select(AgentRun, Conversation, Customer)
                .join(Conversation, Conversation.id == AgentRun.conversation_id)
                .join(Customer, Customer.id == Conversation.customer_id)
                .where(Customer.organization_id == self.organization_id)
                .order_by(AgentRun.created_at.desc())
                .limit(8)
            )
        ).all()
        support_activity = [
            AgentActivity(
                conversation_id=conversation.id,
                session_id=conversation.session_id,
                customer_name=customer.name,
                model=run.model,
                latency_ms=run.latency_ms,
                tokens=run.tokens,
                status=run.status,
                created_at=run.created_at,
            )
            for run, conversation, customer in recent_runs
        ]

        organization = await self.session.get(Organization, self.organization_id)

        return DashboardResponse(
            organization_name=organization.name if organization else None,
            customer_count=customer_count,
            open_ticket_count=open_count,
            resolved_ticket_count=resolved_count,
            escalated_ticket_count=escalated_count,
            conversation_count=conversation_count,
            agent_run_count=agent_run_count,
            memory_event_count=sum(by_operation.values()),
            memory_recall_count=by_operation.get(MemoryOperation.recall.value, 0),
            memory_retain_count=by_operation.get(MemoryOperation.retain.value, 0),
            memory_reflect_count=by_operation.get(MemoryOperation.reflect.value, 0),
            memory_provider=self.memory_provider,
            llm_configured=self.llm_configured,
            memory_activity=activity,
            recent_tickets=[TicketRead.model_validate(t) for t in recent_tickets],
            recent_support_activity=support_activity,
            generated_at=datetime.now(timezone.utc),
        )

    async def analytics(self) -> AnalyticsResponse:
        customer_ids = self._org_customers()

        total_tickets = await self._scalar(
            select(func.count()).select_from(self._org_tickets())
        )
        status_rows = (
            await self.session.execute(
                select(Ticket.status, func.count(Ticket.id))
                .join(Customer, Customer.id == Ticket.customer_id)
                .where(Customer.organization_id == self.organization_id)
                .group_by(Ticket.status)
            )
        ).all()
        by_status = {row[0]: int(row[1]) for row in status_rows}
        open_count = sum(by_status.get(status, 0) for status in OPEN_STATUSES)
        resolved_count = by_status.get(TicketStatus.resolved.value, 0)
        escalated_count = by_status.get(TicketStatus.escalated.value, 0)

        priority_rows = (
            await self.session.execute(
                select(Ticket.priority, func.count(Ticket.id))
                .join(Customer, Customer.id == Ticket.customer_id)
                .where(Customer.organization_id == self.organization_id)
                .group_by(Ticket.priority)
            )
        ).all()
        by_priority = {row[0]: int(row[1]) for row in priority_rows}

        resolved_tickets = (
            await self.session.execute(
                select(Ticket.created_at, Ticket.resolved_at)
                .join(Customer, Customer.id == Ticket.customer_id)
                .where(
                    Customer.organization_id == self.organization_id,
                    Ticket.resolved_at.isnot(None),
                )
            )
        ).all()
        durations = [
            (row[1] - row[0]).total_seconds() / 3600.0
            for row in resolved_tickets
            if row[0] and row[1]
        ]
        average_resolution_hours = round(sum(durations) / len(durations), 2) if durations else None

        run_rows = (
            await self.session.execute(
                select(AgentRun.status, func.count(AgentRun.id), func.avg(AgentRun.latency_ms), func.sum(AgentRun.tokens))
                .join(Conversation, Conversation.id == AgentRun.conversation_id)
                .where(Conversation.customer_id.in_(customer_ids))
                .group_by(AgentRun.status)
            )
        ).all()
        agent_runs = sum(int(row[1]) for row in run_rows)
        successful_runs = sum(int(row[1]) for row in run_rows if row[0] == AgentRunStatus.success.value)
        total_tokens = sum(int(row[3] or 0) for row in run_rows)
        latencies = [float(row[2]) for row in run_rows if row[2] is not None]
        average_latency = round(sum(latencies) / len(latencies), 1) if latencies else None

        memory_rows = (
            await self.session.execute(
                select(MemoryEvent.operation, func.count(MemoryEvent.id))
                .where(MemoryEvent.customer_id.in_(customer_ids))
                .group_by(MemoryEvent.operation)
            )
        ).all()
        by_operation = {row[0]: int(row[1]) for row in memory_rows}

        customer_count = await self._scalar(select(func.count()).select_from(customer_ids.subquery()))
        conversation_count = await self._scalar(
            select(func.count(Conversation.id)).where(Conversation.customer_id.in_(customer_ids))
        )

        rows = (
            await self.session.execute(
                select(Ticket.title, Ticket.description)
                .join(Customer, Customer.id == Ticket.customer_id)
                .where(Customer.organization_id == self.organization_id)
            )
        ).all()
        counter: Counter[str] = Counter(categorize(title, description) for title, description in rows)
        recurring = [
            CategoryCount(category=category, count=count)
            for category, count in counter.most_common()
        ]

        return AnalyticsResponse(
            total_tickets=total_tickets,
            open_tickets=open_count,
            resolved_tickets=resolved_count,
            escalated_tickets=escalated_count,
            resolution_rate=round(resolved_count / total_tickets, 4) if total_tickets else 0.0,
            average_resolution_hours=average_resolution_hours,
            agent_runs=agent_runs,
            successful_agent_runs=successful_runs,
            average_agent_latency_ms=average_latency,
            total_tokens=total_tokens,
            memory_recalls=by_operation.get(MemoryOperation.recall.value, 0),
            memory_retains=by_operation.get(MemoryOperation.retain.value, 0),
            memory_reflects=by_operation.get(MemoryOperation.reflect.value, 0),
            customers=customer_count,
            conversations=conversation_count,
            tickets_by_status=by_status,
            tickets_by_priority=by_priority,
            recurring_issue_categories=recurring,
            generated_at=datetime.now(timezone.utc),
        )
