"""Synthetic demo data for local development.

Run with:

    python -m app.seed.seed_data            # seed if empty
    python -m app.seed.seed_data --force    # wipe the demo org and reseed
    python -m app.seed.seed_data --skip-memory   # do not write to Hindsight

All companies, people and incidents are fictional.
"""

from __future__ import annotations

import argparse
import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password
from app.db.database import SessionLocal, engine
from app.models.agent_run import AgentRun
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.enums import (
    AgentRunStatus,
    CustomerStatus,
    MemoryOperation,
    MessageRole,
    TicketPriority,
    TicketStatus,
    UserRole,
)
from app.models.memory_event import MemoryEvent
from app.models.message import Message
from app.models.organization import Organization
from app.models.resolution import Resolution
from app.models.ticket import Ticket
from app.models.user import User
from app.services.hindsight_service import get_hindsight_service

configure_logging("INFO")
logger = get_logger("seed")

DEMO_ORG_NAME = "RecallDesk Demo Workspace"

USERS = [
    ("Priya Raman", "demo@recalldesk.local", "DemoPassword123!", UserRole.admin),
    ("Daniel Okafor", "daniel.okafor@recalldesk.local", "AgentPassword123!", UserRole.agent),
    ("Sofia Marques", "sofia.marques@recalldesk.local", "ViewerPassword123!", UserRole.viewer),
]

CUSTOMERS = [
    ("Arjun Mehta", "arjun.mehta@arjuntech.example", "Arjun Technologies", CustomerStatus.active),
    ("Elena Rossi", "elena.rossi@novasystems.example", "Nova Systems", CustomerStatus.active),
    ("Kwame Boateng", "kwame.boateng@bluepeaklabs.example", "BluePeak Labs", CustomerStatus.active),
    ("Mei Lin Chen", "mei.chen@vertexcloud.example", "Vertex Cloud", CustomerStatus.active),
    ("Tomas Novak", "tomas.novak@orbitstack.example", "OrbitStack", CustomerStatus.active),
    ("Aisha Rahman", "aisha.rahman@helixpay.example", "HelixPay", CustomerStatus.active),
    ("Daniel Whitfield", "daniel.w@northwind-data.example", "Northwind Data", CustomerStatus.prospect),
    ("Yuki Tanaka", "yuki.tanaka@kaiganworks.example", "Kaigan Works", CustomerStatus.active),
    ("Fatima Al-Sayed", "fatima.alsayed@meridiangrid.example", "Meridian Grid", CustomerStatus.paused),
    ("Lucas Moreau", "lucas.moreau@atlasforge.example", "AtlasForge", CustomerStatus.active),
    ("Grace Njoroge", "grace.njoroge@savannalabs.example", "Savanna Labs", CustomerStatus.churned),
    ("Henrik Lund", "henrik.lund@borealmedia.example", "Boreal Media", CustomerStatus.active),
]

TICKETS = [
    (0, "API latency spikes during peak traffic", "Requests to the public API take 8-20s during business hours.", TicketPriority.critical, TicketStatus.resolved),
    (0, "Connection pool exhaustion on primary database", "API workers exhaust the RDS connection pool and start timing out.", TicketPriority.high, TicketStatus.resolved),
    (0, "Rate limit headers missing on 429 responses", "429s do not include Retry-After after the recent gateway change.", TicketPriority.medium, TicketStatus.open),
    (1, "SSO login loop for new users", "New hires are redirected back to the login page after authenticating.", TicketPriority.high, TicketStatus.investigating),
    (1, "Invoice shows wrong seat count", "August invoice bills 40 seats, the workspace has 28.", TicketPriority.medium, TicketStatus.waiting),
    (2, "Webhook deliveries duplicated", "Order webhooks arrive twice for about 5% of events.", TicketPriority.high, TicketStatus.resolved),
    (2, "Export to CSV times out", "Exporting more than 50k rows fails after 60 seconds.", TicketPriority.medium, TicketStatus.resolved),
    (3, "Postgres 16 upgrade regression on analytics queries", "A dashboard query went from 2s to 90s after the minor version upgrade.", TicketPriority.high, TicketStatus.investigating),
    (3, "Request for staging environment", "Customer wants a dedicated staging environment.", TicketPriority.low, TicketStatus.open),
    (4, "Rolling deploys drop in-flight requests", "During deploys about 1% of requests fail with 502.", TicketPriority.high, TicketStatus.escalated),
    (4, "Migration lock blocks nightly job", "The nightly reconciliation job waits on a table lock for 20 minutes.", TicketPriority.critical, TicketStatus.investigating),
    (5, "PCI audit evidence request", "Customer needs evidence that card data is never logged.", TicketPriority.high, TicketStatus.waiting),
    (5, "Sandbox keys rotate unexpectedly", "Test keys stopped working after a scheduled rotation.", TicketPriority.medium, TicketStatus.resolved),
    (6, "Trial to annual conversion questions", "Pricing and seat questions before signing.", TicketPriority.low, TicketStatus.open),
    (7, "Unicode handling in bulk import", "Non-latin names are mangled during CSV import.", TicketPriority.medium, TicketStatus.resolved),
    (8, "Data residency question for EU customers", "Where is EU data stored and can it be pinned to a region?", TicketPriority.medium, TicketStatus.waiting),
    (9, "Background job retries ignore Retry-After", "The worker ignores 429 backoff headers and hammers the API.", TicketPriority.high, TicketStatus.resolved),
    (9, "Custom role permissions not applied", "A custom role can read billing data it should not see.", TicketPriority.critical, TicketStatus.escalated),
    (10, "Onboarding call request", "Customer wants training for the new workspace.", TicketPriority.low, TicketStatus.open),
    (11, "Slow dashboard on mobile", "Dashboard takes over 20 seconds on the mobile app.", TicketPriority.medium, TicketStatus.investigating),
    (11, "Token expiry shorter than documented", "Tokens expire after 30 minutes, docs say 60.", TicketPriority.medium, TicketStatus.open),
    (0, "Read replica lag affects reports", "Reporting replica lags 20 minutes behind the primary.", TicketPriority.medium, TicketStatus.resolved),
]

RESOLUTIONS = [
    (0, "Pool exhaustion was the root cause of the API timeouts", "Raised max_connections from 100 to 400 on the RDS instance, added pgbouncer in transaction mode, and set pool_recycle to 300s so idle connections are recycled. Latency returned to baseline and error rate dropped to zero.", True),
    (1, "Connection pool exhaustion resolved by raising the limit", "Increased the application pool size and shortened pool lifetime; the API stopped timing out under peak load.", True),
    (3, "Duplicate webhooks were caused by a non-idempotent consumer", "Added an idempotency key check on the consumer side; duplicates stopped after the next deploy.", True),
    (3, "CSV export timeout fixed with streaming and a longer proxy timeout", "Rewrote the export to stream rows instead of buffering them and raised the gateway timeout to 300s.", True),
    (7, "Unicode import fixed by reading files as UTF-8", "Switched the importer to read with explicit UTF-8 encoding; names now round-trip correctly.", True),
    (8, "Worker now honours Retry-After", "Added backoff parsing so the worker respects 429 Retry-After headers instead of retrying immediately.", True),
    (10, "Deployment drop fixed with readiness probes and connection draining", "Added readiness probes and drained connections before restart, which removed the 502s during rolling deploys.", True),
]

CONVERSATIONS = [
    (0, "AWS RDS and PostgreSQL version confirmation", [
        (MessageRole.user, "We're deploying our API to AWS RDS using PostgreSQL 16. Our connection limit is 100."),
        (MessageRole.assistant, "Noted: PostgreSQL 16 on RDS with a connection limit of 100. That limit is the first thing to check if you see timeouts under load."),
    ]),
    (0, "Connection pool incident follow-up", [
        (MessageRole.user, "The API is timing out again, roughly the same errors we saw in June."),
        (MessageRole.assistant, "That matches the earlier incident. Last time the RDS connection limit of 100 was exhausted; the fix was raising the limit and adding a pooler. Do you want me to check the current value?"),
        (MessageRole.user, "Yes please, and note we prefer technical detail in writing."),
    ]),
    (1, "SSO onboarding questions", [
        (MessageRole.user, "New team members cannot complete the SSO login flow on their first attempt."),
        (MessageRole.assistant, "This is usually a SAML assertion or an unverified domain. Can you share the IdP metadata and the exact error on the redirect?"),
    ]),
    (2, "Webhook duplication investigation", [
        (MessageRole.user, "We are seeing duplicate webhook deliveries for roughly 5% of events since Monday."),
        (MessageRole.assistant, "Duplicates usually mean the consumer is retrying without an idempotency key. Do your handlers persist the event id before processing?"),
    ]),
    (3, "Postgres 16 upgrade regression", [
        (MessageRole.user, "After upgrading to PostgreSQL 16 our analytics dashboard went from 2 seconds to 90 seconds."),
        (MessageRole.assistant, "A planner regression after a major version upgrade is common. Can you share EXPLAIN ANALYZE output for the slow query and the previous version for comparison?"),
    ]),
    (4, "Deployment 502s during rolling updates", [
        (MessageRole.user, "About 1% of requests fail with 502 during every rolling deploy."),
        (MessageRole.assistant, "That pattern points to in-flight connections being dropped on restart. Have you added readiness probes and connection draining?"),
    ]),
    (5, "PCI evidence request", [
        (MessageRole.user, "Our auditors need evidence that card data is never written to application logs."),
        (MessageRole.assistant, "I can provide the logging policy and the redaction rules. This needs a compliance owner to sign off, so I am flagging it for review."),
    ]),
    (7, "Bulk import encoding fix", [
        (MessageRole.user, "Names with non-latin characters are mangled when we import a CSV."),
        (MessageRole.assistant, "That is a file encoding issue: the importer is reading the file as the system default. Reading it explicitly as UTF-8 fixes it."),
    ]),
]

AGENT_MODELS = ["openai/gpt-oss-120b", "llama-3.3-70b-versatile"]

# Durable knowledge about the demo customers, written to Hindsight at seed time.
CUSTOMER_MEMORY = {
    0: [
        "Arjun Technologies runs their API on AWS RDS with PostgreSQL 16.",
        "Arjun Technologies has an RDS connection limit of 100 connections.",
        "A previous API timeout incident at Arjun Technologies was caused by connection-pool exhaustion.",
        "Increasing the connection pool size and adding a pooler resolved the previous timeout incident at Arjun Technologies.",
        "Arjun Technologies prefers detailed technical explanations in writing.",
    ],
    1: ["Nova Systems uses SAML SSO with Okta and provisions new users automatically from the IdP."],
    2: ["BluePeak Labs receives duplicated order webhooks; the fix was an idempotency key in the consumer."],
    3: ["Vertex Cloud upgraded to PostgreSQL 16 and saw a planner regression on their analytics queries."],
    4: ["OrbitStack deploys with rolling updates and previously lost in-flight requests during deploys."],
    5: ["HelixPay handles card data and requires PCI evidence before renewals."],
    7: ["Kaigan Works imports customer data from CSV files and requires UTF-8 encoding."],
    9: ["AtlasForge has a custom role configuration that must restrict billing visibility."],
}


async def seed(session: AsyncSession, skip_memory: bool = False, force: bool = False) -> None:
    existing = await session.execute(
        select(Organization).where(Organization.name == DEMO_ORG_NAME)
    )
    organization = existing.scalar_one_or_none()

    if organization and force:
        logger.info("seed.removing_existing_demo_workspace")
        await session.execute(
            delete(User).where(User.organization_id == organization.id)
        )
        await session.execute(
            delete(Customer).where(Customer.organization_id == organization.id)
        )
        await session.execute(delete(Organization).where(Organization.id == organization.id))
        await session.flush()
        organization = None

    if organization:
        logger.info("seed.already_seeded", extra={"organization_id": organization.id})
        return

    organization = Organization(name=DEMO_ORG_NAME, industry="B2B SaaS support")
    session.add(organization)
    await session.flush()

    users: List[User] = []
    for name, email, password, role in USERS:
        if email == settings.seed_demo_email:
            password = settings.seed_demo_password
        user = User(
            name=name,
            email=email,
            password_hash=hash_password(password),
            role=role.value,
            organization_id=organization.id,
        )
        session.add(user)
        users.append(user)
    await session.flush()

    customers: List[Customer] = []
    for name, email, company, status in CUSTOMERS:
        customer = Customer(
            organization_id=organization.id,
            name=name,
            email=email,
            company=company,
            status=status.value,
        )
        session.add(customer)
        customers.append(customer)
    await session.flush()

    now = datetime.now(timezone.utc)
    tickets: List[Ticket] = []
    for index, (customer_index, title, description, priority, status) in enumerate(TICKETS):
        created = now - timedelta(days=30 - index, hours=index)
        ticket = Ticket(
            customer_id=customers[customer_index].id,
            title=title,
            description=description,
            priority=priority.value,
            status=status.value,
            assigned_to=users[1].id,
            created_at=created,
            updated_at=created,
            resolved_at=created + timedelta(hours=6) if status == TicketStatus.resolved else None,
        )
        session.add(ticket)
        tickets.append(ticket)
    await session.flush()

    for ticket_index, summary, solution, successful in RESOLUTIONS:
        ticket = tickets[ticket_index]
        session.add(
            Resolution(
                ticket_id=ticket.id,
                summary=summary,
                solution=solution,
                successful=successful,
            )
        )
    await session.flush()

    conversations: List[Conversation] = []
    for index, (customer_index, _title, messages) in enumerate(CONVERSATIONS):
        created = now - timedelta(days=len(CONVERSATIONS) - index, hours=3 * index)
        conversation = Conversation(
            customer_id=customers[customer_index].id,
            ticket_id=tickets[index % len(tickets)].id if index % 2 == 0 else None,
            session_id=f"seed{index:04d}{index:08d}"[:64],
            created_at=created,
            updated_at=created,
        )
        session.add(conversation)
        conversations.append(conversation)
        for order, (role, content) in enumerate(messages):
            session.add(
                Message(
                    conversation_id=conversation.id,
                    role=role.value,
                    content=content,
                    created_at=created + timedelta(minutes=2 * order),
                )
            )
    await session.flush()

    random.seed(7)
    for conversation in conversations:
        for _ in range(random.randint(1, 3)):
            session.add(
                AgentRun(
                    conversation_id=conversation.id,
                    model=random.choice(AGENT_MODELS),
                    latency_ms=random.randint(700, 4200),
                    tokens=random.randint(400, 3200),
                    status=AgentRunStatus.success.value,
                )
            )
        for _ in range(random.randint(1, 2)):
            operation = random.choice([MemoryOperation.retain, MemoryOperation.recall])
            session.add(
                MemoryEvent(
                    customer_id=conversation.customer_id,
                    conversation_id=conversation.id,
                    operation=operation.value,
                    query="seeded demo activity",
                    memory_count=random.randint(1, 5),
                    provider="seed",
                )
            )
    await session.flush()

    logger.info(
        "seed.database_complete",
        extra={
            "organization_id": organization.id,
            "users": len(users),
            "customers": len(customers),
            "tickets": len(tickets),
            "conversations": len(conversations),
        },
    )

    if skip_memory:
        logger.info("seed.memory_skipped")
        return

    memory = get_hindsight_service()
    if memory.is_demo:
        logger.warning(
            "seed.hindsight_not_configured",
            extra={"hint": "Set HINDSIGHT_API_URL and HINDSIGHT_API_KEY to seed real memories."},
        )
        return

    try:
        await memory.ensure_bank()
        seeded = 0
        for customer_index, facts in CUSTOMER_MEMORY.items():
            customer = customers[customer_index]
            content = "\n".join(f"- {fact}" for fact in facts)
            await memory.retain(
                customer_id=customer.id,
                organization_id=organization.id,
                content=(
                    f"Account profile for {customer.company} ({customer.name}, {customer.email}).\n"
                    f"{content}"
                ),
                context="customer account profile",
                metadata={"source": "seed"},
                entities=[{"text": customer.company or customer.name, "type": "ORG"}],
            )
            seeded += len(facts)
        logger.info("seed.memory_complete", extra={"facts_retained": seeded})
    except Exception as exc:  # noqa: BLE001
        logger.warning("seed.memory_failed", extra={"error": str(exc)})


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed RecallDesk demo data")
    parser.add_argument("--force", action="store_true", help="Delete and recreate demo data")
    parser.add_argument(
        "--skip-memory", action="store_true", help="Skip writing memories to Hindsight"
    )
    args = parser.parse_args()

    async with SessionLocal() as session:
        try:
            await seed(session, skip_memory=args.skip_memory, force=args.force)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    await engine.dispose()
    logger.info("seed.done", extra={"demo_email": settings.seed_demo_email})


if __name__ == "__main__":
    asyncio.run(main())
