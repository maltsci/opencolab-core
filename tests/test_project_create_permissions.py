"""
Regression tests for project creation API permission rules:
- admin, pi, and researcher roles CAN create projects (POST returns 201)
- unauthenticated requests return 401
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

PROJECTS_ENDPOINT = "/api/v1/projects"
CREATE_PAYLOAD = {"name": "Regression Test Project", "description": "API permission test"}


class TestProjectCreateAdminRole:
    """Admin role MUST be able to create projects via POST /api/v1/projects."""

    async def test_post_projects_returns_201(self, client: AsyncClient, auth_headers: dict):
        response = await client.post(
            PROJECTS_ENDPOINT,
            json=CREATE_PAYLOAD,
            headers=auth_headers,
        )
        assert response.status_code == 201

    async def test_post_projects_returns_project_in_body(self, client: AsyncClient, auth_headers: dict):
        response = await client.post(
            PROJECTS_ENDPOINT,
            json=CREATE_PAYLOAD,
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["name"] == CREATE_PAYLOAD["name"]
        assert data["description"] == CREATE_PAYLOAD["description"]


class TestProjectCreatePiRole:
    """PI role MUST be able to create projects via POST /api/v1/projects."""

    async def test_post_projects_returns_201(self, client: AsyncClient, pi_headers: dict):
        response = await client.post(
            PROJECTS_ENDPOINT,
            json=CREATE_PAYLOAD,
            headers=pi_headers,
        )
        assert response.status_code == 201

    async def test_post_projects_returns_project_in_body(self, client: AsyncClient, pi_headers: dict):
        response = await client.post(
            PROJECTS_ENDPOINT,
            json=CREATE_PAYLOAD,
            headers=pi_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["name"] == CREATE_PAYLOAD["name"]


class TestProjectCreateResearcherRole:
    """Researcher role MUST be able to create projects via POST /api/v1/projects."""

    async def test_post_projects_returns_201(self, client: AsyncClient, researcher_headers: dict):
        response = await client.post(
            PROJECTS_ENDPOINT,
            json=CREATE_PAYLOAD,
            headers=researcher_headers,
        )
        assert response.status_code == 201

    async def test_post_projects_returns_project_in_body(
        self, client: AsyncClient, researcher_headers: dict
    ):
        response = await client.post(
            PROJECTS_ENDPOINT,
            json=CREATE_PAYLOAD,
            headers=researcher_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["name"] == CREATE_PAYLOAD["name"]


class TestProjectCreateUnauthenticated:
    """Requests without valid auth MUST be rejected (401 or 403)."""

    async def test_post_projects_without_token_rejected(self, client: AsyncClient):
        response = await client.post(
            PROJECTS_ENDPOINT,
            json=CREATE_PAYLOAD,
        )
        assert response.status_code in (401, 403)

    async def test_post_projects_with_invalid_token_returns_401(self, client: AsyncClient):
        response = await client.post(
            PROJECTS_ENDPOINT,
            json=CREATE_PAYLOAD,
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert response.status_code in (401, 403)
