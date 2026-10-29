import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ResearcherProject
from app.models.source import SessionSource, Source
from app.models.message import Message
from app.models.user import User
from app.services.research_asset_service import materialize_source_asset

pytestmark = pytest.mark.asyncio


async def test_create_session(client: AsyncClient, researcher_headers):
    response = await client.post(
        "/api/v1/sessions",
        json={"title": "Test Session"},
        headers=researcher_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Session"


async def test_create_project_session_links_only_accessible_project_sources(
    client: AsyncClient,
    researcher_headers,
    researcher_user: User,
    admin_user: User,
    db: AsyncSession,
):
    project = Project(name="Project With Sources", description=None)
    source = Source(
        type="file",
        name="project-paper.pdf",
        owner_id=researcher_user.id,
        processing_state="ready",
    )
    restricted_source = Source(
        type="file",
        name="restricted-paper.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
    )
    db.add_all([project, source, restricted_source])
    await db.flush()
    db.add(
        ResearcherProject(
            project_id=project.id,
            researcher_id=researcher_user.id,
            role="owner",
        )
    )
    await materialize_source_asset(
        db=db,
        source=source,
        owner_id=researcher_user.id,
        origin_project_id=project.id,
        origin_session_id=None,
        visibility_scope="project",
        link_type="source",
    )
    restricted_asset = await materialize_source_asset(
        db=db,
        source=restricted_source,
        owner_id=admin_user.id,
        origin_project_id=project.id,
        origin_session_id=None,
        visibility_scope="project",
        link_type="source",
    )
    restricted_asset.classification = "confidential"
    await db.commit()

    response = await client.post(
        "/api/v1/sessions",
        json={"project_id": project.id},
        headers=researcher_headers,
    )

    assert response.status_code == 201
    session_id = response.json()["id"]
    linked_source = await db.scalar(
        select(SessionSource).where(
            SessionSource.session_id == session_id,
            SessionSource.source_id == source.id,
        )
    )
    linked_restricted = await db.scalar(
        select(SessionSource).where(
            SessionSource.session_id == session_id,
            SessionSource.source_id == restricted_source.id,
        )
    )
    assert linked_source is not None
    assert linked_restricted is None


async def test_list_session_available_sources_groups_project_lab_and_private_sources(
    client: AsyncClient,
    researcher_headers,
    researcher_user: User,
    admin_user: User,
    db: AsyncSession,
):
    project = Project(name="Available Sources Project", description=None)
    project_source = Source(
        type="file",
        name="project-paper.pdf",
        owner_id=researcher_user.id,
        processing_state="ready",
    )
    public_source = Source(
        type="file",
        name="lab-public-paper.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
    )
    private_source = Source(
        type="file",
        name="my-private-paper.pdf",
        owner_id=researcher_user.id,
        processing_state="ready",
    )
    lab_private_source = Source(
        type="file",
        name="my-lab-private-paper.pdf",
        owner_id=researcher_user.id,
        processing_state="ready",
    )
    db.add_all([project, project_source, public_source, private_source, lab_private_source])
    await db.flush()
    db.add(
        ResearcherProject(
            project_id=project.id,
            researcher_id=researcher_user.id,
            role="owner",
        )
    )
    await materialize_source_asset(
        db=db,
        source=project_source,
        owner_id=researcher_user.id,
        origin_project_id=project.id,
        origin_session_id=None,
        visibility_scope="project",
        link_type="source",
    )
    await materialize_source_asset(
        db=db,
        source=public_source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_public",
        link_type="source",
    )
    await materialize_source_asset(
        db=db,
        source=private_source,
        owner_id=researcher_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="private",
        link_type="source",
    )
    await materialize_source_asset(
        db=db,
        source=lab_private_source,
        owner_id=researcher_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_private",
        link_type="source",
    )
    await db.commit()

    create_response = await client.post(
        "/api/v1/sessions",
        json={"project_id": project.id},
        headers=researcher_headers,
    )
    assert create_response.status_code == 201
    session_id = create_response.json()["id"]

    response = await client.get(
        f"/api/v1/sessions/{session_id}/available-sources",
        headers=researcher_headers,
    )

    assert response.status_code == 200
    items = response.json()
    by_id = {item["source"]["id"]: item for item in items}
    # Project sources the user can access are linked to the session at
    # creation time, so they no longer appear as available.
    assert project_source.id not in by_id
    linked_project_source = await db.scalar(
        select(SessionSource).where(
            SessionSource.session_id == session_id,
            SessionSource.source_id == project_source.id,
        )
    )
    assert linked_project_source is not None
    assert by_id[public_source.id]["category"] == "lab_public"
    assert by_id[private_source.id]["category"] == "my_materials"
    assert lab_private_source.id not in by_id


async def test_list_sessions(client: AsyncClient, researcher_headers):
    create = await client.post(
        "/api/v1/sessions",
        json={"title": "Listed Session"},
        headers=researcher_headers,
    )
    session_id = create.json()["id"]

    # Empty sessions are excluded by default
    response = await client.get("/api/v1/sessions", headers=researcher_headers)
    assert response.status_code == 200
    assert len(response.json()) == 0

    # Add a message so the session is no longer empty
    await client.post(
        f"/api/v1/sessions/{session_id}/messages",
        json={"content": "hello"},
        headers=researcher_headers,
    )
    response = await client.get("/api/v1/sessions", headers=researcher_headers)
    assert response.status_code == 200
    assert len(response.json()) >= 1
    assert response.json()[0]["message_count"] >= 1

    # include_empty=true returns all sessions
    response = await client.get(
        "/api/v1/sessions?include_empty=true", headers=researcher_headers
    )
    assert response.status_code == 200
    assert len(response.json()) >= 1


async def test_list_session_messages_has_stable_same_timestamp_order(
    client: AsyncClient,
    researcher_headers,
    db: AsyncSession,
):
    create = await client.post(
        "/api/v1/sessions",
        json={"title": "Message Order"},
        headers=researcher_headers,
    )
    session_id = create.json()["id"]

    assistant_message = Message(
        id="same-time-b",
        session_id=session_id,
        role="assistant",
        content="assistant result",
    )
    user_message = Message(
        id="same-time-a",
        session_id=session_id,
        role="user",
        content="user request",
    )
    db.add_all([assistant_message, user_message])
    await db.commit()

    response = await client.get(
        f"/api/v1/sessions/{session_id}/messages",
        headers=researcher_headers,
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [
        "same-time-a",
        "same-time-b",
    ]


async def test_get_session(client: AsyncClient, researcher_headers):
    create = await client.post(
        "/api/v1/sessions",
        json={"title": "Get Session"},
        headers=researcher_headers,
    )
    session_id = create.json()["id"]
    response = await client.get(
        f"/api/v1/sessions/{session_id}", headers=researcher_headers
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Get Session"


async def test_update_session(client: AsyncClient, researcher_headers):
    create = await client.post(
        "/api/v1/sessions",
        json={"title": "Old Title"},
        headers=researcher_headers,
    )
    session_id = create.json()["id"]
    response = await client.put(
        f"/api/v1/sessions/{session_id}",
        json={"title": "New Title"},
        headers=researcher_headers,
    )
    assert response.status_code == 200
    assert response.json()["title"] == "New Title"


async def test_delete_session(client: AsyncClient, researcher_headers):
    create = await client.post(
        "/api/v1/sessions",
        json={"title": "To Delete"},
        headers=researcher_headers,
    )
    session_id = create.json()["id"]
    response = await client.delete(
        f"/api/v1/sessions/{session_id}", headers=researcher_headers
    )
    assert response.status_code == 204


async def test_session_isolation(client: AsyncClient, auth_headers, researcher_headers):
    # Admin creates a session
    create = await client.post(
        "/api/v1/sessions",
        json={"title": "Admin Session"},
        headers=auth_headers,
    )
    session_id = create.json()["id"]

    # Researcher cannot access admin's session
    response = await client.get(
        f"/api/v1/sessions/{session_id}", headers=researcher_headers
    )
    assert response.status_code == 404
