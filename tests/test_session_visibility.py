import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ROLE_RESEARCHER
from app.core.security import create_access_token, hash_password
from app.models.user import User, Workspace

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def member_user(db: AsyncSession) -> User:
    user = User(
        username="member1",
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
async def member_headers(member_user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(member_user.id)}"}


async def _setup_project_with_member_session(
    client: AsyncClient,
    owner_headers: dict,
    member_headers: dict,
    member_id: str,
) -> tuple[str, str]:
    """Create a project (owner), add member, member creates a session in it."""
    create = await client.post(
        "/api/v1/projects", json={"name": "Shared Project"}, headers=owner_headers
    )
    project_id = create.json()["id"]
    await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"researcher_id": member_id},
        headers=owner_headers,
    )
    session = await client.post(
        "/api/v1/sessions",
        json={"title": "Member Session", "project_id": project_id},
        headers=member_headers,
    )
    assert session.status_code == 201
    return project_id, session.json()["id"]


async def test_owner_sees_all_project_sessions(
    client: AsyncClient, researcher_headers, member_headers, member_user
):
    project_id, member_session_id = await _setup_project_with_member_session(
        client, researcher_headers, member_headers, member_user.id
    )
    # Owner also creates their own session in the project
    await client.post(
        "/api/v1/sessions",
        json={"title": "Owner Session", "project_id": project_id},
        headers=researcher_headers,
    )

    # Owner sees both sessions
    response = await client.get(
        f"/api/v1/sessions?project_id={project_id}&include_empty=true",
        headers=researcher_headers,
    )
    assert response.status_code == 200
    titles = {s["title"] for s in response.json()}
    assert titles == {"Member Session", "Owner Session"}
    member_entry = next(s for s in response.json() if s["id"] == member_session_id)
    assert member_entry["owner_id"] == member_user.id
    assert member_entry["owner_name"] == member_user.username

    # Member only sees their own session
    response = await client.get(
        f"/api/v1/sessions?project_id={project_id}&include_empty=true",
        headers=member_headers,
    )
    titles = {s["title"] for s in response.json()}
    assert titles == {"Member Session"}


async def test_owner_can_read_member_session(
    client: AsyncClient, researcher_headers, member_headers, member_user
):
    project_id, member_session_id = await _setup_project_with_member_session(
        client, researcher_headers, member_headers, member_user.id
    )
    response = await client.get(
        f"/api/v1/sessions/{member_session_id}", headers=researcher_headers
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Member Session"

    # Owner can also read the message history
    response = await client.get(
        f"/api/v1/sessions/{member_session_id}/messages", headers=researcher_headers
    )
    assert response.status_code == 200


async def test_member_cannot_read_other_sessions(
    client: AsyncClient, researcher_headers, member_headers, member_user
):
    project_id, _ = await _setup_project_with_member_session(
        client, researcher_headers, member_headers, member_user.id
    )
    owner_session = await client.post(
        "/api/v1/sessions",
        json={"title": "Owner Only", "project_id": project_id},
        headers=researcher_headers,
    )
    owner_session_id = owner_session.json()["id"]
    response = await client.get(
        f"/api/v1/sessions/{owner_session_id}", headers=member_headers
    )
    assert response.status_code == 404


async def test_owner_cannot_modify_member_session(
    client: AsyncClient, researcher_headers, member_headers, member_user
):
    project_id, member_session_id = await _setup_project_with_member_session(
        client, researcher_headers, member_headers, member_user.id
    )
    # Rename is creator-only
    response = await client.put(
        f"/api/v1/sessions/{member_session_id}",
        json={"title": "Hijacked"},
        headers=researcher_headers,
    )
    assert response.status_code == 404
    # Delete is creator-only
    response = await client.delete(
        f"/api/v1/sessions/{member_session_id}", headers=researcher_headers
    )
    assert response.status_code == 404
