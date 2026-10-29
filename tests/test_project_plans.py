import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ROLE_RESEARCHER
from app.core.security import create_access_token, hash_password
from app.models.user import User, Workspace

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


async def _create_project(client: AsyncClient, headers: dict, name: str = "Plan Project") -> str:
    response = await client.post("/api/v1/projects", json={"name": name}, headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


async def _add_member(client: AsyncClient, headers: dict, project_id: str, researcher_id: str):
    response = await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"researcher_id": researcher_id},
        headers=headers,
    )
    assert response.status_code == 201


async def test_create_plan_full_fields(client: AsyncClient, researcher_headers):
    project_id = await _create_project(client, researcher_headers)
    response = await client.post(
        f"/api/v1/projects/{project_id}/plans",
        json={
            "title": "Collect papers",
            "content": "Gather 20 recent papers",
            "start_date": "2026-08-01",
            "due_date": "2026-08-15",
            "priority": "high",
            "tags": ["literature"],
        },
        headers=researcher_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Collect papers"
    assert data["content"] == "Gather 20 recent papers"
    assert data["start_date"] == "2026-08-01"
    assert data["due_date"] == "2026-08-15"
    assert data["priority"] == "high"
    assert data["tags"] == ["literature"]
    assert data["status"] == "todo"
    assert data["assignee_id"] is None


async def test_list_plans_requires_membership(
    client: AsyncClient, researcher_headers, second_headers
):
    project_id = await _create_project(client, researcher_headers)
    await client.post(
        f"/api/v1/projects/{project_id}/plans",
        json={"title": "Secret plan"},
        headers=researcher_headers,
    )
    response = await client.get(
        f"/api/v1/projects/{project_id}/plans", headers=second_headers
    )
    assert response.status_code == 404


async def test_list_plans_filter_by_status(client: AsyncClient, researcher_headers):
    project_id = await _create_project(client, researcher_headers)
    create = await client.post(
        f"/api/v1/projects/{project_id}/plans",
        json={"title": "Plan A"},
        headers=researcher_headers,
    )
    plan_id = create.json()["id"]
    await client.put(
        f"/api/v1/projects/{project_id}/plans/{plan_id}",
        json={"status": "done"},
        headers=researcher_headers,
    )
    await client.post(
        f"/api/v1/projects/{project_id}/plans",
        json={"title": "Plan B"},
        headers=researcher_headers,
    )
    response = await client.get(
        f"/api/v1/projects/{project_id}/plans?status=done",
        headers=researcher_headers,
    )
    assert response.status_code == 200
    titles = [p["title"] for p in response.json()]
    assert titles == ["Plan A"]


async def test_assignee_can_change_status_only(
    client: AsyncClient,
    researcher_headers,
    researcher_user,
    second_headers,
    second_researcher,
):
    project_id = await _create_project(client, researcher_headers)
    await _add_member(client, researcher_headers, project_id, second_researcher.id)
    create = await client.post(
        f"/api/v1/projects/{project_id}/plans",
        json={"title": "Assigned plan", "assignee_id": second_researcher.id},
        headers=researcher_headers,
    )
    assert create.status_code == 201
    assert create.json()["assignee_name"] == second_researcher.username
    plan_id = create.json()["id"]

    # Assignee can change status
    response = await client.put(
        f"/api/v1/projects/{project_id}/plans/{plan_id}",
        json={"status": "in_progress"},
        headers=second_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"

    # Assignee cannot edit other fields
    response = await client.put(
        f"/api/v1/projects/{project_id}/plans/{plan_id}",
        json={"title": "Hijacked"},
        headers=second_headers,
    )
    assert response.status_code == 403


async def test_non_assignee_member_cannot_change_status(
    client: AsyncClient,
    researcher_headers,
    second_headers,
    second_researcher,
):
    project_id = await _create_project(client, researcher_headers)
    await _add_member(client, researcher_headers, project_id, second_researcher.id)
    create = await client.post(
        f"/api/v1/projects/{project_id}/plans",
        json={"title": "Owner plan"},
        headers=researcher_headers,
    )
    plan_id = create.json()["id"]
    response = await client.put(
        f"/api/v1/projects/{project_id}/plans/{plan_id}",
        json={"status": "done"},
        headers=second_headers,
    )
    assert response.status_code == 403


async def test_owner_can_edit_and_delete_plan(
    client: AsyncClient, researcher_headers, second_researcher
):
    project_id = await _create_project(client, researcher_headers)
    await _add_member(client, researcher_headers, project_id, second_researcher.id)
    create = await client.post(
        f"/api/v1/projects/{project_id}/plans",
        json={"title": "Old title"},
        headers=researcher_headers,
    )
    plan_id = create.json()["id"]
    response = await client.put(
        f"/api/v1/projects/{project_id}/plans/{plan_id}",
        json={"title": "New title", "priority": "low", "assignee_id": second_researcher.id},
        headers=researcher_headers,
    )
    assert response.status_code == 200
    assert response.json()["title"] == "New title"
    assert response.json()["priority"] == "low"
    assert response.json()["assignee_id"] == second_researcher.id

    response = await client.delete(
        f"/api/v1/projects/{project_id}/plans/{plan_id}",
        headers=researcher_headers,
    )
    assert response.status_code == 204
    plans = await client.get(
        f"/api/v1/projects/{project_id}/plans", headers=researcher_headers
    )
    assert plans.json() == []


async def test_plan_validation(client: AsyncClient, researcher_headers, second_researcher):
    project_id = await _create_project(client, researcher_headers)
    # Invalid priority
    response = await client.post(
        f"/api/v1/projects/{project_id}/plans",
        json={"title": "Bad", "priority": "urgent"},
        headers=researcher_headers,
    )
    assert response.status_code == 400
    # Assignee must be a project member
    response = await client.post(
        f"/api/v1/projects/{project_id}/plans",
        json={"title": "Bad assignee", "assignee_id": second_researcher.id},
        headers=researcher_headers,
    )
    assert response.status_code == 400
    # Invalid status on update
    create = await client.post(
        f"/api/v1/projects/{project_id}/plans",
        json={"title": "Ok"},
        headers=researcher_headers,
    )
    plan_id = create.json()["id"]
    response = await client.put(
        f"/api/v1/projects/{project_id}/plans/{plan_id}",
        json={"status": "archived"},
        headers=researcher_headers,
    )
    assert response.status_code == 400
