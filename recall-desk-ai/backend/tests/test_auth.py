"""Authentication API tests (require MySQL)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.db

REGISTER_PAYLOAD = {
    "name": "Priya Raman",
    "email": "priya@recalldesk.local",
    "password": "StrongPass123!",
    "organization_name": "Auth Test Workspace",
}


async def test_register_returns_token_and_user(client: AsyncClient):
    response = await client.post("/api/auth/register", json=REGISTER_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == REGISTER_PAYLOAD["email"]
    assert "password_hash" not in response.text
    assert body["user"]["role"] == "agent"


async def test_register_rejects_weak_password(client: AsyncClient):
    payload = {**REGISTER_PAYLOAD, "email": "weak@recalldesk.local", "password": "password"}
    response = await client.post("/api/auth/register", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_register_rejects_duplicate_email(client: AsyncClient):
    await client.post("/api/auth/register", json=REGISTER_PAYLOAD)
    response = await client.post("/api/auth/register", json=REGISTER_PAYLOAD)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


async def test_login_success_and_failure(client: AsyncClient):
    await client.post("/api/auth/register", json=REGISTER_PAYLOAD)

    ok = await client.post(
        "/api/auth/login",
        json={"email": REGISTER_PAYLOAD["email"], "password": REGISTER_PAYLOAD["password"]},
    )
    assert ok.status_code == 200
    assert ok.json()["access_token"]

    bad = await client.post(
        "/api/auth/login",
        json={"email": REGISTER_PAYLOAD["email"], "password": "wrong-password"},
    )
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "AUTHENTICATION_FAILED"


async def test_protected_route_requires_token(client: AsyncClient):
    response = await client.get("/api/customers")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"


async def test_me_returns_current_user(auth_client: AsyncClient):
    response = await auth_client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == "test-admin@recalldesk.local"
    assert response.json()["role"] == "admin"
