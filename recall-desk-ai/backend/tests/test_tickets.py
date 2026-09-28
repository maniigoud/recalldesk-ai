"""Ticket API tests (require MySQL)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.db


async def _customer(auth_client: AsyncClient, name: str = "Arjun Technologies") -> dict:
    response = await auth_client.post(
        "/api/customers",
        json={
            "name": name,
            "email": f"{name.split()[0].lower()}@example.test",
            "company": name,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _ticket(auth_client: AsyncClient, customer_id: int, **overrides) -> dict:
    payload = {
        "customer_id": customer_id,
        "title": "API latency spikes",
        "description": "Requests take 8-20s during peak hours.",
        "priority": "high",
    }
    payload.update(overrides)
    response = await auth_client.post("/api/tickets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_ticket(auth_client: AsyncClient):
    customer = await _customer(auth_client)
    ticket = await _ticket(auth_client, customer["id"])

    assert ticket["status"] == "open"
    assert ticket["priority"] == "high"
    assert ticket["customer_id"] == customer["id"]


async def test_list_tickets_with_filters(auth_client: AsyncClient):
    customer = await _customer(auth_client)
    await _ticket(auth_client, customer["id"], priority="high")
    await _ticket(
        auth_client,
        customer["id"],
        title="Billing question",
        priority="low",
        status="waiting",
    )

    high = await auth_client.get("/api/tickets", params={"priority": "high"})
    assert high.json()["total"] == 1

    waiting = await auth_client.get("/api/tickets", params={"status": "waiting"})
    assert waiting.json()["total"] == 1
    assert waiting.json()["items"][0]["title"] == "Billing question"

    by_customer = await auth_client.get(
        "/api/tickets", params={"customer_id": customer["id"]}
    )
    assert by_customer.json()["total"] == 2


async def test_ticket_detail_and_resolution(auth_client: AsyncClient):
    customer = await _customer(auth_client)
    ticket = await _ticket(auth_client, customer["id"])

    detail = await auth_client.get(f"/api/tickets/{ticket['id']}")
    assert detail.status_code == 200
    assert detail.json()["customer_name"] == "Arjun Technologies"
    assert detail.json()["resolutions"] == []

    resolved = await auth_client.put(
        f"/api/tickets/{ticket['id']}",
        json={
            "ticket": {"status": "resolved"},
            "resolution": {
                "summary": "Pool exhaustion was the root cause",
                "solution": "Raised max_connections to 400 and added pgbouncer.",
                "successful": True,
            },
        },
    )
    assert resolved.status_code == 200
    body = resolved.json()
    assert body["status"] == "resolved"
    assert body["resolved_at"] is not None
    assert len(body["resolutions"]) == 1
    assert body["resolutions"][0]["successful"] is True

    # Updating again must upsert, not duplicate.
    again = await auth_client.put(
        f"/api/tickets/{ticket['id']}",
        json={
            "ticket": {"status": "resolved"},
            "resolution": {
                "summary": "Pool exhaustion was the root cause (confirmed)",
                "solution": "Raised max_connections to 500.",
                "successful": True,
            },
        },
    )
    assert len(again.json()["resolutions"]) == 1


async def test_missing_ticket_returns_404(auth_client: AsyncClient):
    response = await auth_client.get("/api/tickets/999999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TICKET_NOT_FOUND"
