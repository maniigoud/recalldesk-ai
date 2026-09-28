"""Shared pytest fixtures.

Unit tests run without any external service. Tests that need MySQL are marked
``@pytest.mark.db`` and are skipped automatically when the database cannot be
reached, so the suite never requires credentials to run.

When the database is available the whole application is pointed at
``TEST_DATABASE_URL`` (default ``.../recall_desk_test``) so tests never touch
the development data.
"""

from __future__ import annotations

import asyncio
import os
from typing import AsyncIterator, Optional

import pytest
import pytest_asyncio

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "mysql+aiomysql://root:password@localhost:3306/recall_desk_test"
)

# Must happen before the application modules are imported.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("HINDSIGHT_API_KEY", "")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-that-is-long-enough-for-hs256")

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.database import engine  # noqa: E402
from app.main import app  # noqa: E402

_db_available: Optional[bool] = None


def database_available() -> bool:
    global _db_available
    if _db_available is None:
        try:

            async def probe() -> bool:
                try:
                    async with engine.connect() as connection:
                        await connection.execute(text("SELECT 1"))
                    return True
                except Exception:  # noqa: BLE001
                    return False

            _db_available = asyncio.run(probe())
        except Exception:  # noqa: BLE001
            _db_available = False
    return _db_available


def pytest_collection_modifyitems(config, items):
    if database_available():
        return
    skip = pytest.mark.skip(
        reason="MySQL test database is not reachable (set TEST_DATABASE_URL)"
    )
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def prepared_database():
    if not database_available():
        pytest.skip("MySQL test database is not reachable")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(loop_scope="session")
async def client(prepared_database) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient) -> AsyncIterator[AsyncClient]:
    """Client with a valid admin token for a freshly registered organization."""
    response = await client.post(
        "/api/auth/register",
        json={
            "name": "Test Admin",
            "email": "test-admin@recalldesk.local",
            "password": "TestPassword123!",
            "organization_name": "Test Workspace",
        },
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    yield client
    client.headers.pop("Authorization", None)
