import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ROLE_RESEARCHER
from app.core.security import create_access_token, hash_password
from app.models.source import Source
from app.models.user import User, Workspace
from app.services.research_asset_service import materialize_source_asset

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def second_researcher(db: AsyncSession) -> User:
    user = User(
        username="researcher2",
        hashed_password=hash_password("pass123"),
        role=ROLE_RESEARCHER,
    )
    db.add(user)
    await db.flush()
    db.add(Workspace(researcher_id=user.id))
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def second_headers(second_researcher: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(second_researcher.id)}"}


async def _create_project(client: AsyncClient, headers: dict, name: str = "Feed Project") -> str:
    response = await client.post("/api/v1/projects", json={"name": name}, headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


async def _activity_actions(
    client: AsyncClient, headers: dict, project_id: str
) -> list[dict]:
    response = await client.get(
        f"/api/v1/projects/{project_id}/activities", headers=headers
    )
    assert response.status_code == 200
    return response.json()


async def test_project_creation_logged(client: AsyncClient, researcher_headers, researcher_user):
    project_id = await _create_project(client, researcher_headers)
    activities = await _activity_actions(client, researcher_headers, project_id)
    assert len(activities) == 1
    entry = activities[0]
    assert entry["action"] == "project_created"
    assert entry["target_title"] == "Feed Project"
    assert entry["actor_name"] == researcher_user.username


async def test_member_add_remove_logged(
    client: AsyncClient, researcher_headers, second_researcher
):
    project_id = await _create_project(client, researcher_headers)
    await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"researcher_id": second_researcher.id},
        headers=researcher_headers,
    )
    await client.delete(
        f"/api/v1/projects/{project_id}/members/{second_researcher.id}",
        headers=researcher_headers,
    )
    activities = await _activity_actions(client, researcher_headers, project_id)
    actions = sorted(a["action"] for a in activities)
    assert actions == ["member_added", "member_removed", "project_created"]
    removed = next(a for a in activities if a["action"] == "member_removed")
    added = next(a for a in activities if a["action"] == "member_added")
    assert removed["target_title"] == second_researcher.username
    assert added["target_title"] == second_researcher.username


async def test_session_creation_logged(client: AsyncClient, researcher_headers):
    project_id = await _create_project(client, researcher_headers)
    response = await client.post(
        "/api/v1/sessions",
        json={"title": "Chat about gaps", "project_id": project_id},
        headers=researcher_headers,
    )
    assert response.status_code == 201
    activities = await _activity_actions(client, researcher_headers, project_id)
    session_entries = [a for a in activities if a["action"] == "session_created"]
    assert len(session_entries) == 1
    assert session_entries[0]["target_title"] == "Chat about gaps"


async def test_plan_events_logged(client: AsyncClient, researcher_headers, second_researcher):
    project_id = await _create_project(client, researcher_headers)
    await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"researcher_id": second_researcher.id},
        headers=researcher_headers,
    )
    create = await client.post(
        f"/api/v1/projects/{project_id}/plans",
        json={"title": "Draft report", "assignee_id": second_researcher.id},
        headers=researcher_headers,
    )
    plan_id = create.json()["id"]
    await client.put(
        f"/api/v1/projects/{project_id}/plans/{plan_id}",
        json={"status": "in_progress"},
        headers=researcher_headers,
    )
    activities = await _activity_actions(client, researcher_headers, project_id)
    actions = [a["action"] for a in activities]
    assert "plan_created" in actions
    assert "plan_assigned" in actions
    assert "plan_status_changed" in actions
    status_entry = next(a for a in activities if a["action"] == "plan_status_changed")
    assert "todo -> in_progress" in status_entry["target_title"]


async def test_activities_require_membership(
    client: AsyncClient, researcher_headers, second_headers
):
    project_id = await _create_project(client, researcher_headers)
    response = await client.get(
        f"/api/v1/projects/{project_id}/activities", headers=second_headers
    )
    assert response.status_code == 404


async def test_activities_limit(client: AsyncClient, researcher_headers, second_researcher):
    project_id = await _create_project(client, researcher_headers)
    for i in range(5):
        await client.post(
            f"/api/v1/projects/{project_id}/plans",
            json={"title": f"Plan {i}"},
            headers=researcher_headers,
        )
    response = await client.get(
        f"/api/v1/projects/{project_id}/activities?limit=3",
        headers=researcher_headers,
    )
    assert response.status_code == 200
    assert len(response.json()) == 3


async def test_bulk_asset_link_is_project_activity_projection(
    client: AsyncClient,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
):
    project_id = await _create_project(client, auth_headers, "Resource projection")
    source = Source(
        type="file",
        name="Projection resource.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    db.add(source)
    await db.flush()
    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_public",
        link_type="reference",
    )
    await db.commit()

    payload = {
        "asset_ids": [asset.id],
        "project_ids": [project_id],
        "link_type": "reference",
    }
    first = await client.post(
        "/api/v1/library/assets/bulk-link",
        json=payload,
        headers=auth_headers,
    )
    assert first.status_code == 200
    second = await client.post(
        "/api/v1/library/assets/bulk-link",
        json=payload,
        headers=auth_headers,
    )
    assert second.status_code == 200

    activities = await _activity_actions(client, auth_headers, project_id)
    asset_links = [
        activity
        for activity in activities
        if activity["action"] == "asset_linked" and activity["target_id"] == asset.id
    ]
    assert len(asset_links) == 1
    assert asset_links[0]["target_title"] == "Projection resource.pdf"


async def test_generated_asset_is_project_activity_projection(
    client: AsyncClient,
    auth_headers,
):
    project_id = await _create_project(client, auth_headers, "Generated output")

    response = await client.post(
        f"/api/v1/projects/{project_id}/assets",
        json={
            "project_id": project_id,
            "title": "Research summary",
            "content": "A generated summary of the current evidence.",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200

    activities = await _activity_actions(client, auth_headers, project_id)
    generated = [
        activity
        for activity in activities
        if activity["action"] == "asset_generated"
    ]
    assert len(generated) == 1
    assert generated[0]["target_id"] == response.json()["id"]
    assert generated[0]["target_title"] == "Research summary"
