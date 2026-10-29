import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_create_project_allowed_for_researcher(client: AsyncClient, researcher_headers):
    response = await client.post(
        "/api/v1/projects",
        json={"name": "Researcher Project", "description": "A test"},
        headers=researcher_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Researcher Project"
    assert data["is_owner"] is True


async def test_create_project(client: AsyncClient, pi_headers):
    response = await client.post(
        "/api/v1/projects",
        json={"name": "Test Project", "description": "A test"},
        headers=pi_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Project"
    return data["id"]


async def test_list_projects_admin_sees_all(client: AsyncClient, auth_headers, researcher_headers):
    # Admin creates a project
    await client.post(
        "/api/v1/projects",
        json={"name": "Admin Project"},
        headers=auth_headers,
    )
    # Admin lists - should see all projects
    response = await client.get("/api/v1/projects", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) >= 1
    assert any(p["name"] == "Admin Project" for p in response.json())


async def test_list_projects_researcher_sees_own_only(client: AsyncClient, auth_headers, researcher_headers):
    # Admin creates a project (researcher is NOT a member)
    await client.post(
        "/api/v1/projects",
        json={"name": "Admin Only Project"},
        headers=auth_headers,
    )
    # Researcher creates their own project
    await client.post(
        "/api/v1/projects",
        json={"name": "Researcher Own Project"},
        headers=researcher_headers,
    )
    # Researcher lists - should NOT see admin's project, only their own
    response = await client.get("/api/v1/projects", headers=researcher_headers)
    assert response.status_code == 200
    names = [p["name"] for p in response.json()]
    assert "Researcher Own Project" in names
    assert "Admin Only Project" not in names


async def test_list_projects_scope_joined_filters_for_privileged(
    client: AsyncClient, auth_headers, pi_headers
):
    # Admin creates a project (PI is NOT a member)
    await client.post(
        "/api/v1/projects",
        json={"name": "Admin Private Project"},
        headers=auth_headers,
    )
    # PI creates their own project
    await client.post(
        "/api/v1/projects",
        json={"name": "PI Own Project"},
        headers=pi_headers,
    )
    # Default scope still returns everything for privileged roles
    response = await client.get("/api/v1/projects", headers=pi_headers)
    names = [p["name"] for p in response.json()]
    assert "Admin Private Project" in names
    # scope=joined only returns projects the PI participates in
    response = await client.get("/api/v1/projects?scope=joined", headers=pi_headers)
    names = [p["name"] for p in response.json()]
    assert "PI Own Project" in names
    assert "Admin Private Project" not in names


async def test_get_project_any_user(client: AsyncClient, auth_headers, researcher_headers):
    # Admin creates a project
    create = await client.post(
        "/api/v1/projects",
        json={"name": "Get Project"},
        headers=auth_headers,
    )
    project_id = create.json()["id"]
    # Researcher (not a member) can view it
    response = await client.get(
        f"/api/v1/projects/{project_id}", headers=researcher_headers
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Get Project"


async def test_project_knowledge_context_is_member_scoped(
    client: AsyncClient,
    auth_headers,
    researcher_headers,
    researcher_user,
    pi_headers,
):
    project = await client.post(
        "/api/v1/projects",
        json={"name": "Knowledge Context Project"},
        headers=auth_headers,
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    add_member = await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"researcher_id": researcher_user.id, "role": "member"},
        headers=auth_headers,
    )
    assert add_member.status_code == 201

    direction = await client.post(
        "/api/v1/research-directions",
        json={"name": "Project Knowledge Direction", "summary": "Linked context"},
        headers=auth_headers,
    )
    assert direction.status_code == 201
    link = await client.post(
        f"/api/v1/research-directions/{direction.json()['id']}/projects",
        json={"project_id": project_id},
        headers=auth_headers,
    )
    assert link.status_code == 201

    response = await client.get(
        f"/api/v1/projects/{project_id}/knowledge-context",
        headers=researcher_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert {member["id"] for member in payload["members"]} >= {researcher_user.id}
    assert payload["directions"] == [
        {
            "id": direction.json()["id"],
            "name": "Project Knowledge Direction",
            "summary": "Linked context",
        }
    ]

    privileged = await client.get(
        f"/api/v1/projects/{project_id}/knowledge-context",
        headers=pi_headers,
    )
    assert privileged.status_code == 200
    assert privileged.json()["directions"] == payload["directions"]


async def test_update_project(client: AsyncClient, auth_headers):
    create = await client.post(
        "/api/v1/projects",
        json={"name": "Old Name"},
        headers=auth_headers,
    )
    project_id = create.json()["id"]
    response = await client.put(
        f"/api/v1/projects/{project_id}",
        json={"name": "New Name"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"


async def test_delete_project(client: AsyncClient, auth_headers):
    create = await client.post(
        "/api/v1/projects",
        json={"name": "To Delete"},
        headers=auth_headers,
    )
    project_id = create.json()["id"]
    response = await client.delete(
        f"/api/v1/projects/{project_id}", headers=auth_headers
    )
    assert response.status_code == 204


async def test_project_instructions_roundtrip(client: AsyncClient, researcher_headers):
    create = await client.post(
        "/api/v1/projects",
        json={"name": "Instr Project", "instructions": "# Role\nYou are a helper."},
        headers=researcher_headers,
    )
    assert create.status_code == 201
    project_id = create.json()["id"]
    assert create.json()["instructions"] == "# Role\nYou are a helper."

    response = await client.get(
        f"/api/v1/projects/{project_id}", headers=researcher_headers
    )
    assert response.json()["instructions"] == "# Role\nYou are a helper."

    # Update instructions
    response = await client.put(
        f"/api/v1/projects/{project_id}",
        json={"instructions": "new instructions"},
        headers=researcher_headers,
    )
    assert response.status_code == 200
    assert response.json()["instructions"] == "new instructions"

    # Update without instructions leaves them unchanged
    response = await client.put(
        f"/api/v1/projects/{project_id}",
        json={"description": "desc only"},
        headers=researcher_headers,
    )
    assert response.json()["instructions"] == "new instructions"

    # Explicit null clears instructions
    response = await client.put(
        f"/api/v1/projects/{project_id}",
        json={"instructions": None},
        headers=researcher_headers,
    )
    assert response.json()["instructions"] is None


async def test_create_project_associates_scoped_tasks(
    client: AsyncClient, researcher_headers, db
):
    from app.models.task_definition import TaskDefinitionRecord

    scoped_task = TaskDefinitionRecord(
        id="scoped-task",
        name="Scoped Task",
        description="Only for specific projects",
        workflow_id="literature_synthesizer",
        project_ids=["other-project"],
    )
    global_task = TaskDefinitionRecord(
        id="global-task",
        name="Global Task",
        description="Visible everywhere",
        workflow_id="literature_synthesizer",
        project_ids=[],
    )
    db.add_all([scoped_task, global_task])
    await db.commit()

    create = await client.post(
        "/api/v1/projects",
        json={
            "name": "Task Assoc Project",
            "task_ids": ["scoped-task", "global-task", "missing-task"],
        },
        headers=researcher_headers,
    )
    assert create.status_code == 201
    project_id = create.json()["id"]
    # The selection is stored on the project, including global tasks
    assert create.json()["task_ids"] == ["scoped-task", "global-task", "missing-task"]

    await db.refresh(scoped_task)
    await db.refresh(global_task)
    assert project_id in scoped_task.project_ids
    # Other scopes are preserved
    assert "other-project" in scoped_task.project_ids
    # Global tasks stay global
    assert global_task.project_ids == []

    # The stored selection is editable
    response = await client.put(
        f"/api/v1/projects/{project_id}",
        json={"task_ids": ["global-task"]},
        headers=researcher_headers,
    )
    assert response.status_code == 200
    assert response.json()["task_ids"] == ["global-task"]


async def test_create_group_scoped_to_project(client: AsyncClient, auth_headers, researcher_headers):
    create = await client.post(
        "/api/v1/projects",
        json={"name": "Collection Project"},
        headers=auth_headers,
    )
    project_id = create.json()["id"]

    # Non-member cannot bind a collection to the project
    response = await client.post(
        "/api/v1/sources/groups",
        json={"name": "Forbidden Collection", "project_id": project_id},
        headers=researcher_headers,
    )
    assert response.status_code == 404

    # Owner creates a collection bound to the project
    response = await client.post(
        "/api/v1/sources/groups",
        json={"name": "Project Collection", "project_id": project_id},
        headers=auth_headers,
    )
    assert response.status_code == 201

    # The collection shows up as a project asset
    response = await client.get(
        f"/api/v1/projects/{project_id}/assets", headers=auth_headers
    )
    assert response.status_code == 200
    titles = [a["title"] for a in response.json()]
    assert "Project Collection" in titles

    # Groups created without project_id stay unlinked
    await client.post(
        "/api/v1/sources/groups",
        json={"name": "Loose Collection"},
        headers=auth_headers,
    )
    response = await client.get(
        f"/api/v1/projects/{project_id}/assets", headers=auth_headers
    )
    titles = [a["title"] for a in response.json()]
    assert "Loose Collection" not in titles
