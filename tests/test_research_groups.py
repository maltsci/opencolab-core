from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_group import ResearchGroup, ResearchGroupMember
from app.models.user import User
from app.services.research_group_service import is_active_group_member

pytestmark = pytest.mark.asyncio


async def _create_group(
    client: AsyncClient,
    headers: dict,
    *,
    name: str,
) -> dict:
    response = await client.post(
        "/api/v1/research-groups",
        json={"name": name, "description": f"{name} description"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def test_admin_can_create_research_group(
    client: AsyncClient,
    auth_headers: dict,
) -> None:
    group = await _create_group(client, auth_headers, name="Lab A")

    assert group["name"] == "Lab A"
    assert group["archived_at"] is None


async def test_pi_member_can_manage_membership_for_own_group(
    client: AsyncClient,
    auth_headers: dict,
    pi_headers: dict,
    pi_user: User,
    researcher_user: User,
) -> None:
    group = await _create_group(client, auth_headers, name="PI Lab")
    add_pi = await client.post(
        f"/api/v1/research-groups/{group['id']}/members",
        json={"user_id": pi_user.id, "role": "pi"},
        headers=auth_headers,
    )
    assert add_pi.status_code == 201

    response = await client.post(
        f"/api/v1/research-groups/{group['id']}/members",
        json={"user_id": researcher_user.id, "role": "phd_student"},
        headers=pi_headers,
    )

    assert response.status_code == 201
    assert response.json()["role"] == "phd_student"


async def test_researcher_cannot_add_themself_to_another_group(
    client: AsyncClient,
    auth_headers: dict,
    researcher_headers: dict,
    researcher_user: User,
) -> None:
    group = await _create_group(client, auth_headers, name="Protected Lab")

    response = await client.post(
        f"/api/v1/research-groups/{group['id']}/members",
        json={"user_id": researcher_user.id, "role": "assistant"},
        headers=researcher_headers,
    )

    assert response.status_code == 403


async def test_user_can_hold_different_roles_in_different_groups(
    client: AsyncClient,
    auth_headers: dict,
    researcher_user: User,
    db: AsyncSession,
) -> None:
    group_a = await _create_group(client, auth_headers, name="Lab Role A")
    group_b = await _create_group(client, auth_headers, name="Lab Role B")

    for group_id, role in (
        (group_a["id"], "postdoc"),
        (group_b["id"], "external_collaborator"),
    ):
        response = await client.post(
            f"/api/v1/research-groups/{group_id}/members",
            json={"user_id": researcher_user.id, "role": role},
            headers=auth_headers,
        )
        assert response.status_code == 201

    memberships = (
        await db.execute(
            select(ResearchGroupMember)
            .where(ResearchGroupMember.user_id == researcher_user.id)
            .order_by(ResearchGroupMember.role)
        )
    ).scalars().all()

    assert {membership.role for membership in memberships} == {
        "external_collaborator",
        "postdoc",
    }


async def test_archived_group_and_removed_membership_are_inactive(
    db: AsyncSession,
    admin_user: User,
    researcher_user: User,
) -> None:
    group = ResearchGroup(name="Archived Lab", created_by=admin_user.id)
    db.add(group)
    await db.flush()
    membership = ResearchGroupMember(
        group_id=group.id,
        user_id=researcher_user.id,
        role="assistant",
        created_by=admin_user.id,
    )
    db.add(membership)
    await db.flush()

    assert await is_active_group_member(
        db,
        group_id=group.id,
        user_id=researcher_user.id,
    )

    membership.removed_at = datetime.now(timezone.utc)
    await db.flush()
    assert not await is_active_group_member(
        db,
        group_id=group.id,
        user_id=researcher_user.id,
    )

    membership.removed_at = None
    group.archived_at = datetime.now(timezone.utc)
    await db.flush()
    assert not await is_active_group_member(
        db,
        group_id=group.id,
        user_id=researcher_user.id,
    )


async def test_admin_can_create_project_for_research_group(
    client: AsyncClient,
    auth_headers: dict,
) -> None:
    group = await _create_group(client, auth_headers, name="Project Lab")

    response = await client.post(
        "/api/v1/projects",
        json={"name": "Governed Project", "research_group_id": group["id"]},
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["research_group_id"] == group["id"]
