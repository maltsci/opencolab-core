"""
Tests for project member management permission rules:
- Researcher who is a non-owner member cannot add or remove members.
- Researcher who is the project owner can add and remove members.
- Admin/PI can always manage members.
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_project(client: AsyncClient, headers: dict, name: str = "Test Project") -> str:
    resp = await client.post("/api/v1/projects", json={"name": name}, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


async def _add_member(client: AsyncClient, headers: dict, project_id: str, researcher_id: str) -> int:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"researcher_id": researcher_id, "role": "member"},
        headers=headers,
    )
    return resp.status_code


async def _remove_member(client: AsyncClient, headers: dict, project_id: str, researcher_id: str) -> int:
    resp = await client.delete(
        f"/api/v1/projects/{project_id}/members/{researcher_id}",
        headers=headers,
    )
    return resp.status_code


async def test_non_owner_researcher_cannot_add_member(
    client: AsyncClient, auth_headers, researcher_headers, researcher_user, pi_user
):
    """Researcher who is a non-owner member must be forbidden from adding members."""
    project_id = await _create_project(client, auth_headers, "Admin Project")

    # Admin shares project with researcher (as member, not owner)
    await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"researcher_id": researcher_user.id, "role": "member"},
        headers=auth_headers,
    )

    # Researcher tries to add pi_user — must be rejected
    status = await _add_member(client, researcher_headers, project_id, pi_user.id)
    assert status == 403


async def test_non_owner_researcher_cannot_remove_member(
    client: AsyncClient, auth_headers, researcher_headers, researcher_user, pi_user
):
    """Researcher who is a non-owner member must be forbidden from removing members."""
    project_id = await _create_project(client, auth_headers, "Admin Project")

    # Admin adds both researcher and pi_user as members
    await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"researcher_id": researcher_user.id, "role": "member"},
        headers=auth_headers,
    )
    await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"researcher_id": pi_user.id, "role": "member"},
        headers=auth_headers,
    )

    # Researcher tries to remove pi_user — must be rejected
    status = await _remove_member(client, researcher_headers, project_id, pi_user.id)
    assert status == 403


async def test_owner_researcher_can_add_member(
    client: AsyncClient, researcher_headers, pi_user
):
    """Researcher who owns the project can add members."""
    project_id = await _create_project(client, researcher_headers, "Researcher Project")

    status = await _add_member(client, researcher_headers, project_id, pi_user.id)
    assert status == 201


async def test_owner_researcher_can_remove_member(
    client: AsyncClient, auth_headers, researcher_headers, researcher_user, pi_user
):
    """Researcher who owns the project can remove members."""
    project_id = await _create_project(client, researcher_headers, "Researcher Project")

    # Admin adds pi_user as a member
    await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"researcher_id": pi_user.id, "role": "member"},
        headers=auth_headers,
    )

    status = await _remove_member(client, researcher_headers, project_id, pi_user.id)
    assert status == 204


async def test_admin_can_add_member_to_any_project(
    client: AsyncClient, auth_headers, researcher_headers, researcher_user, pi_user
):
    """Admin can add members to any project, including ones they did not create."""
    project_id = await _create_project(client, researcher_headers, "Researcher Project")

    status = await _add_member(client, auth_headers, project_id, pi_user.id)
    assert status == 201


async def test_admin_can_remove_member_from_any_project(
    client: AsyncClient, auth_headers, researcher_headers, researcher_user, pi_user
):
    """Admin can remove members from any project."""
    project_id = await _create_project(client, researcher_headers, "Researcher Project")

    # Add pi_user first
    await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"researcher_id": pi_user.id, "role": "member"},
        headers=researcher_headers,
    )

    status = await _remove_member(client, auth_headers, project_id, pi_user.id)
    assert status == 204


async def test_pi_can_change_project_owner(
    client: AsyncClient, pi_headers, researcher_headers, researcher_user, pi_user
):
    project_id = await _create_project(client, researcher_headers, "Owner Transfer Project")
    add_response = await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"researcher_id": pi_user.id, "role": "member"},
        headers=pi_headers,
    )
    assert add_response.status_code == 201

    response = await client.put(
        f"/api/v1/projects/{project_id}/members/{pi_user.id}",
        json={"role": "owner"},
        headers=pi_headers,
    )

    assert response.status_code == 200
    members_response = await client.get(
        f"/api/v1/projects/{project_id}/members",
        headers=pi_headers,
    )
    roles = {
        item["researcher_id"]: item["role"]
        for item in members_response.json()
    }
    assert roles[pi_user.id] == "owner"
    assert roles[researcher_user.id] == "member"
