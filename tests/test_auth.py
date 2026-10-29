import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ROLE_ADMIN

pytestmark = pytest.mark.asyncio


async def test_login_success(client: AsyncClient, admin_user):
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "testadmin", "password": "admin123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert data["user"]["username"] == "testadmin"
    assert data["user"]["role"] == ROLE_ADMIN


async def test_login_wrong_password(client: AsyncClient, admin_user):
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "testadmin", "password": "wrong"},
    )
    assert response.status_code == 401


async def test_login_nonexistent_user(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "noone", "password": "123"},
    )
    assert response.status_code == 401


async def test_archived_member_cannot_login_or_use_existing_token(
    client: AsyncClient,
    researcher_headers: dict[str, str],
    researcher_user,
    db: AsyncSession,
):
    from datetime import UTC, datetime

    researcher_user.archived_at = datetime.now(UTC)
    await db.commit()

    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "researcher1", "password": "pass123"},
    )
    assert login.status_code == 401

    existing_session = await client.get("/api/v1/auth/me", headers=researcher_headers)
    assert existing_session.status_code == 401


async def test_get_me(client: AsyncClient, auth_headers):
    response = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["username"] == "testadmin"


async def test_get_me_no_token(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code in (401, 403)


async def test_logout(client: AsyncClient, auth_headers):
    response = await client.post("/api/v1/auth/logout", headers=auth_headers)
    assert response.status_code == 204
