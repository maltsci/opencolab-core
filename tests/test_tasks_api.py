import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_definition import TaskDefinitionRecord

pytestmark = pytest.mark.asyncio
DEFAULT_TASK_IDS = {
    "core-ideas",
    "experiment-design",
    "hypothesis-generator",
    "literatures-briefs",
    "project-qa",
    "research-gaps",
}


async def _create_project(
    client: AsyncClient,
    headers: dict,
    *,
    name: str,
) -> str:
    response = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"name": name},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _create_task_definition(
    client: AsyncClient,
    headers: dict,
    *,
    task_id: str,
    workflow_id: str = "reviewer_assistant",
    project_ids: list[str] | None = None,
    is_enabled: bool = True,
):
    return await client.post(
        "/api/v1/admin/tasks",
        headers=headers,
        json={
            "id": task_id,
            "version": 1,
            "name": "Reviewer Assistant Task",
            "description": "Researcher-facing reviewer task.",
            "workflow_id": workflow_id,
            "input_schema": {"type": "object", "required": ["review_comments"]},
            "starter_prompts": ["Help me address reviewer comments."],
            "project_context_policy": {"mode": "project_optional"},
            "result_presentation": {"type": "markdown"},
            "is_enabled": is_enabled,
            "project_ids": project_ids or [],
        },
    )


async def test_list_tasks_returns_default_research_tasks(
    client: AsyncClient,
    researcher_headers: dict,
):
    response = await client.get("/api/v1/tasks", headers=researcher_headers)

    assert response.status_code == 200
    task_ids = {item["id"] for item in response.json()}
    assert DEFAULT_TASK_IDS.issubset(task_ids)


async def test_admin_created_task_is_visible_in_public_list(
    client: AsyncClient,
    auth_headers: dict,
    researcher_headers: dict,
):
    create_response = await _create_task_definition(
        client,
        auth_headers,
        task_id="reviewer-task",
    )

    assert create_response.status_code == 201
    assert create_response.json()["id"] == "reviewer-task"

    list_response = await client.get("/api/v1/tasks", headers=researcher_headers)

    assert list_response.status_code == 200
    task_ids = {item["id"] for item in list_response.json()}
    assert DEFAULT_TASK_IDS.issubset(task_ids)
    assert "reviewer-task" in task_ids


async def test_list_tasks_filters_by_project_id(
    client: AsyncClient,
    auth_headers: dict,
    researcher_headers: dict,
):
    visible_project_id = await _create_project(
        client,
        researcher_headers,
        name="Visible Project",
    )
    hidden_project_id = await _create_project(
        client,
        researcher_headers,
        name="Hidden Project",
    )

    create_response = await _create_task_definition(
        client,
        auth_headers,
        task_id="project-task",
        project_ids=[visible_project_id],
    )
    assert create_response.status_code == 201

    visible_response = await client.get(
        f"/api/v1/tasks?project_id={visible_project_id}",
        headers=researcher_headers,
    )
    hidden_response = await client.get(
        f"/api/v1/tasks?project_id={hidden_project_id}",
        headers=researcher_headers,
    )

    assert visible_response.status_code == 200
    visible_ids = {item["id"] for item in visible_response.json()}
    hidden_ids = {item["id"] for item in hidden_response.json()}
    assert DEFAULT_TASK_IDS.issubset(visible_ids)
    assert "project-task" in visible_ids
    assert hidden_response.status_code == 200
    assert DEFAULT_TASK_IDS.issubset(hidden_ids)
    assert "project-task" not in hidden_ids


async def test_project_scoped_task_is_hidden_without_project_id(
    client: AsyncClient,
    auth_headers: dict,
    researcher_headers: dict,
):
    project_id = await _create_project(
        client,
        researcher_headers,
        name="Scoped Project",
    )

    create_response = await _create_task_definition(
        client,
        auth_headers,
        task_id="scoped-task",
        project_ids=[project_id],
    )
    assert create_response.status_code == 201

    list_response = await client.get("/api/v1/tasks", headers=researcher_headers)

    assert list_response.status_code == 200
    task_ids = {item["id"] for item in list_response.json()}
    assert DEFAULT_TASK_IDS.issubset(task_ids)
    assert "scoped-task" not in task_ids


async def test_non_member_cannot_access_other_project_tasks(
    client: AsyncClient,
    auth_headers: dict,
    researcher_headers: dict,
):
    project_id = await _create_project(
        client,
        auth_headers,
        name="Admin Project",
    )
    create_response = await _create_task_definition(
        client,
        auth_headers,
        task_id="admin-project-task",
        project_ids=[project_id],
    )
    assert create_response.status_code == 201

    response = await client.get(
        f"/api/v1/tasks?project_id={project_id}",
        headers=researcher_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


async def test_disabled_task_is_hidden_from_public_list(
    client: AsyncClient,
    auth_headers: dict,
    researcher_headers: dict,
):
    create_response = await _create_task_definition(
        client,
        auth_headers,
        task_id="disabled-task",
        is_enabled=False,
    )
    assert create_response.status_code == 201

    response = await client.get("/api/v1/tasks", headers=researcher_headers)

    assert response.status_code == 200
    task_ids = {item["id"] for item in response.json()}
    assert DEFAULT_TASK_IDS.issubset(task_ids)
    assert "disabled-task" not in task_ids


async def test_disabled_default_task_is_hidden_from_public_list(
    client: AsyncClient,
    researcher_headers: dict,
    db: AsyncSession,
):
    # A disabled DB record must override the code default instead of letting
    # the default task reappear in the enabled list.
    db.add(
        TaskDefinitionRecord(
            id="core-ideas",
            version=1,
            name="提炼核心观点",
            description="disabled default override",
            workflow_id="literature_synthesizer",
            input_schema={"type": "object"},
            starter_prompts=[],
            project_context_policy={},
            result_presentation={},
            is_enabled=False,
            project_ids=[],
        )
    )
    await db.commit()

    response = await client.get("/api/v1/tasks", headers=researcher_headers)

    assert response.status_code == 200
    task_ids = {item["id"] for item in response.json()}
    assert "core-ideas" not in task_ids
    assert (DEFAULT_TASK_IDS - {"core-ideas"}).issubset(task_ids)


async def test_get_disabled_default_task_returns_404(
    client: AsyncClient,
    researcher_headers: dict,
    db: AsyncSession,
):
    db.add(
        TaskDefinitionRecord(
            id="research-gaps",
            version=1,
            name="发现研究空白",
            description="disabled default override",
            workflow_id="literature_synthesizer",
            input_schema={"type": "object"},
            starter_prompts=[],
            project_context_policy={},
            result_presentation={},
            is_enabled=False,
            project_ids=[],
        )
    )
    await db.commit()

    response = await client.get("/api/v1/tasks/research-gaps", headers=researcher_headers)

    assert response.status_code == 404


async def test_admin_can_enable_existing_task(
    client: AsyncClient,
    auth_headers: dict,
    researcher_headers: dict,
):
    create_response = await _create_task_definition(
        client,
        auth_headers,
        task_id="draft-task",
        is_enabled=False,
    )
    assert create_response.status_code == 201

    hidden_response = await client.get("/api/v1/tasks", headers=researcher_headers)
    assert hidden_response.status_code == 200
    hidden_ids = {item["id"] for item in hidden_response.json()}
    assert DEFAULT_TASK_IDS.issubset(hidden_ids)
    assert "draft-task" not in hidden_ids

    update_response = await client.patch(
        "/api/v1/admin/tasks/draft-task",
        headers=auth_headers,
        json={"is_enabled": True},
    )
    assert update_response.status_code == 200
    assert update_response.json()["is_enabled"] is True

    visible_response = await client.get("/api/v1/tasks", headers=researcher_headers)
    assert visible_response.status_code == 200
    visible_ids = {item["id"] for item in visible_response.json()}
    assert DEFAULT_TASK_IDS.issubset(visible_ids)
    assert "draft-task" in visible_ids


async def test_admin_can_update_custom_task_details(
    client: AsyncClient,
    auth_headers: dict,
):
    create_response = await _create_task_definition(
        client,
        auth_headers,
        task_id="editable-task",
    )
    assert create_response.status_code == 201

    update_response = await client.patch(
        "/api/v1/admin/tasks/editable-task",
        headers=auth_headers,
        json={
            "name": "Updated Task",
            "description": "Updated task description.",
            "workflow_id": "literature_synthesizer",
            "input_schema": {"type": "object", "required": ["query"]},
            "starter_prompts": ["Summarize project materials."],
            "project_context_policy": {"inherit_project_sources": True},
            "result_presentation": {"primary_output_key": "overview"},
            "is_enabled": True,
            "project_ids": [],
        },
    )

    assert update_response.status_code == 200
    payload = update_response.json()
    assert payload["name"] == "Updated Task"
    assert payload["workflow_id"] == "literature_synthesizer"
    assert payload["input_schema"]["required"] == ["query"]
    assert payload["project_context_policy"]["inherit_project_sources"] is True


async def test_admin_can_delete_custom_task(
    client: AsyncClient,
    auth_headers: dict,
    researcher_headers: dict,
):
    create_response = await _create_task_definition(
        client,
        auth_headers,
        task_id="delete-me-task",
    )
    assert create_response.status_code == 201

    delete_response = await client.delete(
        "/api/v1/admin/tasks/delete-me-task",
        headers=auth_headers,
    )
    assert delete_response.status_code == 204

    get_response = await client.get(
        "/api/v1/tasks/delete-me-task",
        headers=researcher_headers,
    )
    assert get_response.status_code == 404


async def test_admin_cannot_delete_builtin_task(
    client: AsyncClient,
    auth_headers: dict,
):
    response = await client.delete(
        "/api/v1/admin/tasks/research-gaps",
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Built-in tasks cannot be deleted"


async def test_get_unknown_task_returns_404(
    client: AsyncClient,
    researcher_headers: dict,
):
    response = await client.get(
        "/api/v1/tasks/unknown-task",
        headers=researcher_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


async def test_get_task_requires_matching_project_scope(
    client: AsyncClient,
    auth_headers: dict,
    researcher_headers: dict,
):
    project_id = await _create_project(
        client,
        researcher_headers,
        name="Visible Project",
    )
    other_project_id = await _create_project(
        client,
        researcher_headers,
        name="Other Project",
    )
    create_response = await _create_task_definition(
        client,
        auth_headers,
        task_id="scoped-detail-task",
        project_ids=[project_id],
    )
    assert create_response.status_code == 201

    no_scope_response = await client.get(
        "/api/v1/tasks/scoped-detail-task",
        headers=researcher_headers,
    )
    matching_scope_response = await client.get(
        f"/api/v1/tasks/scoped-detail-task?project_id={project_id}",
        headers=researcher_headers,
    )
    mismatched_scope_response = await client.get(
        f"/api/v1/tasks/scoped-detail-task?project_id={other_project_id}",
        headers=researcher_headers,
    )

    assert no_scope_response.status_code == 404
    assert no_scope_response.json()["detail"] == "Task not found"
    assert matching_scope_response.status_code == 200
    assert matching_scope_response.json()["id"] == "scoped-detail-task"
    assert mismatched_scope_response.status_code == 404
    assert mismatched_scope_response.json()["detail"] == "Task not found"


async def test_get_global_task_allows_project_context(
    client: AsyncClient,
    auth_headers: dict,
    researcher_headers: dict,
):
    project_id = await _create_project(
        client,
        researcher_headers,
        name="Global Task Project",
    )
    create_response = await _create_task_definition(
        client,
        auth_headers,
        task_id="global-detail-task",
    )
    assert create_response.status_code == 201

    response = await client.get(
        f"/api/v1/tasks/global-detail-task?project_id={project_id}",
        headers=researcher_headers,
    )

    assert response.status_code == 200
    assert response.json()["id"] == "global-detail-task"


async def test_create_task_rejects_unknown_workflow_id(
    client: AsyncClient,
    auth_headers: dict,
):
    response = await _create_task_definition(
        client,
        auth_headers,
        task_id="bad-task",
        workflow_id="unknown_workflow",
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Referenced workflow not found: unknown_workflow"


async def test_create_task_rejects_duplicate_task_id(
    client: AsyncClient,
    auth_headers: dict,
):
    first_response = await _create_task_definition(
        client,
        auth_headers,
        task_id="duplicate-task",
    )
    second_response = await _create_task_definition(
        client,
        auth_headers,
        task_id="duplicate-task",
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "A custom task with this id already exists"
