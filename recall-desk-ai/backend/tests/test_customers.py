"""Customer API tests (require MySQL)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.db

CUSTOMER = {
    "name": "Arjun Mehta",
    "email": "arjun.mehta@arjuntech.example",
    "company": "Arjun Technologies",
    "status": "active",
}


async def _create(auth_client: AsyncClient, **overrides) -> dict:
    payload = {**CUSTOMER, **overrides}
    response = await auth_client.post("/api/customers", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_customer(auth_client: AsyncClient):
    customer = await _create(auth_client)
    assert customer["name"] == "Arjun Mehta"
    assert customer["organization_id"] > 0
    assert customer["status"] == "active"


async def test_duplicate_email_is_rejected(auth_client: AsyncClient):
    await _create(auth_client)
    response = await auth_client.post("/api/customers", json=CUSTOMER)
    assert response.status_code == 409


async def test_list_and_search(auth_client: AsyncClient):
    await _create(auth_client)
    await _create(
        auth_client,
        email="elena@novasystems.example",
        name="Elena Rossi",
        company="Nova Systems",
    )

    listed = await auth_client.get("/api/customers")
    assert listed.status_code == 200
    assert listed.json()["total"] == 2

    found = await auth_client.get("/api/customers", params={"search": "nova"})
    assert found.json()["total"] == 1
    assert found.json()["items"][0]["company"] == "Nova Systems"


async def test_customer_detail_includes_summary(auth_client: AsyncClient):
    customer = await _create(auth_client)
    response = await auth_client.get(f"/api/customers/{customer['id']}")

    assert response.status_code == 200
    body = response.json()
    for key in (
        "ticket_count",
        "open_ticket_count",
        "resolved_ticket_count",
        "conversation_count",
        "memory_count",
        "recent_tickets",
        "recent_memories",
    ):
        assert key in body
    assert body["ticket_count"] == 0
    assert body["memory_count"] == 0


async def test_update_and_delete(auth_client: AsyncClient):
    customer = await _create(auth_client)

    updated = await auth_client.put(
        f"/api/customers/{customer['id']}", json={"status": "paused", "company": "Arjun Tech Ltd"}
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "paused"

    deleted = await auth_client.delete(f"/api/customers/{customer['id']}")
    assert deleted.status_code == 204

    missing = await auth_client.get(f"/api/customers/{customer['id']}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "CUSTOMER_NOT_FOUND"


async def test_customer_is_organization_scoped(client: AsyncClient, auth_client: AsyncClient):
    customer = await _create(auth_client)

    other = await client.post(
        "/api/auth/register",
        json={
            "name": "Other Admin",
            "email": "other-admin@recalldesk.local",
            "password": "OtherPass123!",
            "organization_name": "Other Workspace",
        },
    )
    token = other.json()["access_token"]

    response = await client.get(
        f"/api/customers/{customer['id']}", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404
