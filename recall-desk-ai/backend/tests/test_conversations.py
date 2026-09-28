"""Conversation session tests (require MySQL).

The important guarantee: a NEW session starts with an empty transcript but the
customer's persistent memory is untouched.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.db


async def _customer(auth_client: AsyncClient) -> dict:
    response = await auth_client.post(
        "/api/customers",
        json={"name": "Arjun Mehta", "email": "arjun@example.test", "company": "Arjun Technologies"},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_session_and_store_messages(auth_client: AsyncClient):
    customer = await _customer(auth_client)

    conversation = await auth_client.post(
        f"/api/customers/{customer['id']}/conversations", json={}
    )
    assert conversation.status_code == 201
    body = conversation.json()
    assert body["session_id"]
    assert body["message_count"] == 0

    await auth_client.post(
        f"/api/conversations/{body['id']}/messages",
        json={"role": "user", "content": "We run PostgreSQL 16 on AWS RDS."},
    )
    await auth_client.post(
        f"/api/conversations/{body['id']}/messages",
        json={"role": "assistant", "content": "Understood."},
    )

    messages = await auth_client.get(f"/api/conversations/{body['id']}/messages")
    assert messages.status_code == 200
    assert [m["role"] for m in messages.json()] == ["user", "assistant"]


async def test_new_session_has_empty_transcript(auth_client: AsyncClient):
    customer = await _customer(auth_client)
    first = await auth_client.post(
        f"/api/customers/{customer['id']}/conversations", json={}
    )
    await auth_client.post(
        f"/api/conversations/{first.json()['id']}/messages",
        json={"role": "user", "content": "Our connection limit is 100."},
    )

    second = await auth_client.post(
        f"/api/customers/{customer['id']}/conversations", json={}
    )
    assert second.json()["id"] != first.json()["id"]
    assert second.json()["session_id"] != first.json()["session_id"]

    messages = await auth_client.get(f"/api/conversations/{second.json()['id']}/messages")
    assert messages.json() == []

    # The first session is still intact.
    first_messages = await auth_client.get(
        f"/api/conversations/{first.json()['id']}/messages"
    )
    assert len(first_messages.json()) == 1


async def test_list_conversations_for_customer(auth_client: AsyncClient):
    customer = await _customer(auth_client)
    for _ in range(2):
        await auth_client.post(f"/api/customers/{customer['id']}/conversations", json={})

    listed = await auth_client.get(f"/api/customers/{customer['id']}/conversations")
    assert listed.status_code == 200
    assert listed.json()["total"] == 2


async def test_conversation_of_unknown_customer_returns_404(auth_client: AsyncClient):
    response = await auth_client.post("/api/customers/999999/conversations", json={})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CUSTOMER_NOT_FOUND"
