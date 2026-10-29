from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.access_policy import AccessPolicy
from app.models.message import Message
from app.models.research_object import ResearchObject, ResearchObjectRelation
from app.models.source import SessionSource, Source
from app.models.trace import ResearchTrace
from app.models.workflow_run import StepRun, WorkflowRun
from app.services.research_asset_service import materialize_source_asset

pytestmark = pytest.mark.asyncio
AUTH_FAILURE_STATUSES = {401, 403}


async def _create_session(client: AsyncClient, headers: dict) -> str:
    response = await client.post(
        "/api/v1/sessions",
        json={"title": "Workflow API Session"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _create_project_session(
    client: AsyncClient,
    headers: dict,
    *,
    project_id: str,
    title: str,
) -> str:
    response = await client.post(
        "/api/v1/sessions",
        json={"project_id": project_id, "title": title},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _create_project(client: AsyncClient, headers: dict, name: str) -> str:
    response = await client.post(
        "/api/v1/projects",
        json={"name": name},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _create_workflow_run(
    db: AsyncSession,
    *,
    session_id: str,
    user_id: str,
    status: str = "completed",
) -> WorkflowRun:
    workflow_run = WorkflowRun(
        workflow_id="reviewer_assistant",
        workflow_version=1,
        session_id=session_id,
        status=status,
        input_payload={"review_comments": "Address novelty."},
        output_payload={"summary": "Workflow output"},
        created_by=user_id,
    )
    db.add(workflow_run)
    await db.commit()
    await db.refresh(workflow_run)
    return workflow_run


async def test_list_builtin_workflows(client: AsyncClient, researcher_headers: dict):
    response = await client.get("/api/v1/workflows", headers=researcher_headers)

    assert response.status_code == 200
    workflow_ids = {item["id"] for item in response.json()}
    assert "literature_synthesizer" in workflow_ids
    assert "reviewer_assistant" in workflow_ids


async def test_read_endpoints_require_authentication(client: AsyncClient):
    endpoints = [
        "/api/v1/workflows",
        "/api/v1/workflows/reviewer_assistant",
    ]

    for endpoint in endpoints:
        response = await client.get(endpoint)
        assert response.status_code in AUTH_FAILURE_STATUSES


async def test_get_unknown_workflow_returns_404(
    client: AsyncClient,
    researcher_headers: dict,
):
    response = await client.get(
        "/api/v1/workflows/unknown_workflow",
        headers=researcher_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Workflow not found"


async def test_run_builtin_workflow_creates_run_steps_and_trace(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
    monkeypatch,
):
    session_id = await _create_session(client, researcher_headers)

    async def fake_runner(**_kwargs):
        return {
            "output": {"agent": "reviewer_assistant", "summary": "Address concerns"},
            "steps": [
                {
                    "name": "retrieve",
                    "status": "completed",
                    "summary": "retrieved 0 chunks",
                },
                {"name": "format_output", "status": "completed", "summary": "formatted"},
            ],
            "trace_payload": {
                "inputs": {"review_comments": "Please address novelty."},
                "retrieval": [],
                "citations": [],
                "summary_steps": ["retrieved 0 chunks", "formatted"],
            },
        }

    monkeypatch.setattr("app.api.workflows.run_agent_definition", fake_runner)

    response = await client.post(
        "/api/v1/workflows/reviewer_assistant/run",
        headers=researcher_headers,
        json={
            "session_id": session_id,
            "input": {"review_comments": "Please address novelty."},
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["workflow_id"] == "reviewer_assistant"
    assert payload["status"] == "completed"
    assert payload["output_payload"]["summary"] == "Address concerns"

    workflow_run = await db.scalar(
        select(WorkflowRun).where(WorkflowRun.id == payload["id"])
    )
    assert workflow_run is not None
    assert workflow_run.created_by == researcher_user.id

    steps = (
        await db.execute(select(StepRun).where(StepRun.workflow_run_id == payload["id"]))
    ).scalars().all()
    assert len(steps) >= 1

    trace = await db.scalar(
        select(ResearchTrace).where(ResearchTrace.workflow_run_id == payload["id"])
    )
    assert trace is not None
    assert trace.session_id == session_id
    assert trace.user_id == researcher_user.id
    assert trace.message_id is not None

    assistant_message = await db.scalar(
        select(Message).where(Message.id == trace.message_id)
    )
    assert assistant_message is not None
    assert assistant_message.session_id == session_id
    assert assistant_message.role == "assistant"
    assert "Address concerns" in assistant_message.content


@pytest.mark.parametrize("explicit_empty_selection", [False, True])
async def test_run_workflow_respects_explicit_empty_source_selection(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
    monkeypatch,
    explicit_empty_selection: bool,
):
    project_id = await _create_project(
        client,
        researcher_headers,
        "Project Context Sources",
    )
    material_session_id = await _create_project_session(
        client,
        researcher_headers,
        project_id=project_id,
        title="Material Session",
    )
    task_session_id = await _create_project_session(
        client,
        researcher_headers,
        project_id=project_id,
        title="Task Session",
    )
    session_source = Source(
        type="file",
        name="project-paper.pdf",
        owner_id=researcher_user.id,
    )
    unrelated_source = Source(
        type="file",
        name="unrelated-project-paper.pdf",
        owner_id=researcher_user.id,
    )
    db.add_all([session_source, unrelated_source])
    await db.flush()
    governed_asset = await materialize_source_asset(
        db=db,
        source=session_source,
        owner_id=researcher_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_public",
        link_type="source",
    )
    db.add(
        AccessPolicy(
            research_asset_id=governed_asset.id,
            asset_revision_id=governed_asset.current_revision_id,
            subject_type="user",
            subject_id=researcher_user.id,
            capabilities_json=["content:use_in_agent"],
            created_by=researcher_user.id,
        )
    )
    db.add(SessionSource(session_id=task_session_id, source_id=session_source.id))
    db.add(SessionSource(session_id=material_session_id, source_id=unrelated_source.id))
    await db.commit()

    captured_source_ids: list[str] = []

    async def fake_runner(**kwargs):
        captured_source_ids.extend(kwargs["source_ids"])
        return {
            "output": {"agent": "reviewer_assistant", "summary": "Project context used"},
            "steps": [{"name": "retrieve", "status": "completed"}],
            "trace_payload": {
                "inputs": {
                    "review_comments": "Please address novelty.",
                    "source_ids": kwargs["source_ids"],
                },
                "retrieval": [],
                "citations": [],
                "summary_steps": [],
            },
        }

    monkeypatch.setattr("app.api.workflows.run_agent_definition", fake_runner)

    response = await client.post(
        "/api/v1/workflows/reviewer_assistant/run",
        headers=researcher_headers,
        json={
            "session_id": task_session_id,
            "input": {
                "review_comments": "Please address novelty.",
                **({"source_ids": []} if explicit_empty_selection else {}),
            },
        },
    )

    assert response.status_code == 201
    assert captured_source_ids == ([] if explicit_empty_selection else [session_source.id])

    linked_source = await db.scalar(
        select(SessionSource).where(
            SessionSource.session_id == task_session_id,
            SessionSource.source_id == session_source.id,
        )
    )
    assert linked_source is not None

    unrelated_link = await db.scalar(
        select(SessionSource).where(
            SessionSource.session_id == task_session_id,
            SessionSource.source_id == unrelated_source.id,
        )
    )
    assert unrelated_link is None


async def test_run_workflow_requires_raw_sources_linked_to_session(
    client: AsyncClient,
    researcher_headers: dict,
    monkeypatch,
):
    session_id = await _create_session(client, researcher_headers)
    runner_called = False

    async def fake_runner(**_kwargs):
        nonlocal runner_called
        runner_called = True
        return {}

    monkeypatch.setattr("app.api.workflows.run_agent_definition", fake_runner)

    response = await client.post(
        "/api/v1/workflows/reviewer_assistant/run",
        headers=researcher_headers,
        json={
            "session_id": session_id,
            "input": {
                "review_comments": "Please address novelty.",
                "source_ids": ["unlinked-source-id"],
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "All selected sources must be linked to the session."
    )
    assert runner_called is False


async def test_run_workflow_rejects_non_list_source_ids(
    client: AsyncClient,
    researcher_headers: dict,
    monkeypatch,
):
    session_id = await _create_session(client, researcher_headers)
    runner_called = False

    async def fake_runner(**_kwargs):
        nonlocal runner_called
        runner_called = True
        return {}

    monkeypatch.setattr("app.api.workflows.run_agent_definition", fake_runner)

    response = await client.post(
        "/api/v1/workflows/reviewer_assistant/run",
        headers=researcher_headers,
        json={
            "session_id": session_id,
            "input": {
                "review_comments": "Please address novelty.",
                "source_ids": "source-1",
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "source_ids must be a list when provided"
    assert runner_called is False


async def test_get_workflow_run_and_steps_respect_owner(
    client: AsyncClient,
    auth_headers: dict,
    researcher_headers: dict,
    monkeypatch,
):
    session_id = await _create_session(client, auth_headers)

    async def fake_runner(**_kwargs):
        return {
            "output": {"agent": "reviewer_assistant", "summary": "Admin run"},
            "steps": [{"name": "retrieve", "status": "completed"}],
            "trace_payload": {
                "inputs": {"review_comments": "Admin only"},
                "retrieval": [],
                "citations": [],
                "summary_steps": [],
            },
        }

    monkeypatch.setattr("app.api.workflows.run_agent_definition", fake_runner)
    create_response = await client.post(
        "/api/v1/workflows/reviewer_assistant/run",
        headers=auth_headers,
        json={
            "session_id": session_id,
            "input": {"review_comments": "Admin only"},
        },
    )
    assert create_response.status_code == 201
    run_id = create_response.json()["id"]

    own_run_response = await client.get(
        f"/api/v1/workflow-runs/{run_id}",
        headers=auth_headers,
    )
    assert own_run_response.status_code == 200
    assert own_run_response.json()["id"] == run_id

    own_steps_response = await client.get(
        f"/api/v1/workflow-runs/{run_id}/steps",
        headers=auth_headers,
    )
    assert own_steps_response.status_code == 200
    assert [step["step_id"] for step in own_steps_response.json()]

    other_run_response = await client.get(
        f"/api/v1/workflow-runs/{run_id}",
        headers=researcher_headers,
    )
    assert other_run_response.status_code == 404

    other_steps_response = await client.get(
        f"/api/v1/workflow-runs/{run_id}/steps",
        headers=researcher_headers,
    )
    assert other_steps_response.status_code == 404


async def test_list_session_workflow_runs_returns_runs_for_owned_session(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
):
    session_id = await _create_session(client, researcher_headers)
    workflow_run = await _create_workflow_run(
        db,
        session_id=session_id,
        user_id=researcher_user.id,
    )

    response = await client.get(
        f"/api/v1/sessions/{session_id}/workflow-runs",
        headers=researcher_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == [workflow_run.id]
    assert payload[0]["status"] == "completed"


async def test_failed_workflow_run_audit_persists_after_runner_failure(
    client: AsyncClient,
    researcher_headers: dict,
    db: AsyncSession,
    monkeypatch,
):
    session_id = await _create_session(client, researcher_headers)

    async def failing_runner(**_kwargs):
        raise RuntimeError("synthetic workflow failure")

    monkeypatch.setattr("app.api.workflows.run_agent_definition", failing_runner)

    response = await client.post(
        "/api/v1/workflows/reviewer_assistant/run",
        headers=researcher_headers,
        json={
            "session_id": session_id,
            "input": {"review_comments": "Please address novelty."},
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Workflow execution failed."

    failed_run = await db.scalar(
        select(WorkflowRun).where(WorkflowRun.session_id == session_id)
    )
    assert failed_run is not None
    assert failed_run.status == "failed"
    assert failed_run.error_message == "Workflow execution failed."

    steps = (
        await db.execute(
            select(StepRun)
            .where(StepRun.workflow_run_id == failed_run.id)
            .order_by(StepRun.created_at)
        )
    ).scalars().all()
    assert steps
    assert any(step.status == "failed" for step in steps)


async def test_cancel_pending_workflow_run(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
):
    session_id = await _create_session(client, researcher_headers)
    workflow_run = WorkflowRun(
        workflow_id="reviewer_assistant",
        workflow_version=1,
        session_id=session_id,
        status="pending",
        input_payload={},
        created_by=researcher_user.id,
    )
    db.add(workflow_run)
    await db.commit()
    await db.refresh(workflow_run)

    response = await client.post(
        f"/api/v1/workflow-runs/{workflow_run.id}/cancel",
        headers=researcher_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


async def test_save_completed_workflow_run_to_memory_creates_research_object(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
):
    session_id = await _create_session(client, researcher_headers)
    workflow_run = await _create_workflow_run(
        db,
        session_id=session_id,
        user_id=researcher_user.id,
    )
    base_time = datetime(2026, 1, 1, tzinfo=UTC)
    older_trace = ResearchTrace(
        session_id=session_id,
        user_id=researcher_user.id,
        workflow_run_id=workflow_run.id,
        inputs_json={"source_ids": ["old-source"]},
        citations_json=[],
        created_at=base_time,
    )
    latest_trace = ResearchTrace(
        session_id=session_id,
        user_id=researcher_user.id,
        workflow_run_id=workflow_run.id,
        inputs_json={"source_ids": ["source-1", "source-2"]},
        citations_json=[],
        created_at=base_time + timedelta(seconds=1),
    )
    db.add_all([older_trace, latest_trace])
    await db.commit()

    response = await client.post(
        f"/api/v1/workflow-runs/{workflow_run.id}/save-memory",
        headers=researcher_headers,
        json={
            "type": "hypothesis",
            "title": "Workflow hypothesis",
            "content": "Workflow generated insight",
            "relation": {"enabled": False},
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["research_object"]["type"] == "hypothesis"
    assert payload["research_object"]["title"] == "Workflow hypothesis"
    assert payload["relation"] is None

    saved_object = await db.scalar(
        select(ResearchObject).where(
            ResearchObject.id == payload["research_object"]["id"]
        )
    )
    assert saved_object is not None
    assert saved_object.created_by == researcher_user.id
    assert saved_object.content_json["session_id"] == session_id
    assert saved_object.content_json["origin"] == "workflow_run"
    assert saved_object.content_json["workflow_run_id"] == workflow_run.id
    assert saved_object.content_json["trace_id"] == latest_trace.id
    assert saved_object.content_json["source_ids"] == ["source-1", "source-2"]


async def test_save_workflow_run_to_memory_creates_relation_with_trace_evidence(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
):
    session_id = await _create_session(client, researcher_headers)
    workflow_run = await _create_workflow_run(
        db,
        session_id=session_id,
        user_id=researcher_user.id,
    )
    trace = ResearchTrace(
        session_id=session_id,
        user_id=researcher_user.id,
        workflow_run_id=workflow_run.id,
        inputs_json={"source_ids": ["source-1"]},
        citations_json=[
            {
                "source_id": "source-1",
                "chunk_id": "chunk-1",
                "snippet": "workflow evidence",
            }
        ],
    )
    target_object = ResearchObject(
        type="discussion",
        title="Existing object",
        content="Saved earlier",
        content_json={"session_id": session_id},
        created_by=researcher_user.id,
    )
    db.add_all([trace, target_object])
    await db.commit()

    response = await client.post(
        f"/api/v1/workflow-runs/{workflow_run.id}/save-memory",
        headers=researcher_headers,
        json={
            "type": "hypothesis",
            "title": "Workflow hypothesis",
            "content": "Workflow generated insight",
            "relation": {
                "enabled": True,
                "relation_type": "supports",
                "target_object_id": target_object.id,
                "note": "User confirmed workflow evidence.",
            },
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["relation"]["relation_type"] == "supports"
    assert payload["relation"]["target_object"]["id"] == target_object.id
    assert payload["relation"]["metadata_json"]["confidence"] == 0.8
    assert payload["relation"]["metadata_json"]["evidence"]["trace_id"] == trace.id
    assert (
        payload["relation"]["metadata_json"]["evidence"]["citations"][0]["snippet"]
        == "workflow evidence"
    )
    assert (
        payload["relation"]["metadata_json"]["evidence"]["note"]
        == "User confirmed workflow evidence."
    )


async def test_save_workflow_run_to_memory_rejects_non_completed_run(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
):
    session_id = await _create_session(client, researcher_headers)
    workflow_run = await _create_workflow_run(
        db,
        session_id=session_id,
        user_id=researcher_user.id,
        status="running",
    )

    response = await client.post(
        f"/api/v1/workflow-runs/{workflow_run.id}/save-memory",
        headers=researcher_headers,
        json={
            "type": "discussion",
            "title": "Incomplete workflow",
            "content": "Should not be saved",
            "relation": {"enabled": False},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only completed workflow runs can be saved to memory"


async def test_save_workflow_run_to_memory_returns_409_on_relation_integrity_error(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
    monkeypatch,
):
    session_id = await _create_session(client, researcher_headers)
    workflow_run = await _create_workflow_run(
        db,
        session_id=session_id,
        user_id=researcher_user.id,
    )
    target_object = ResearchObject(
        type="discussion",
        title="Existing object",
        content_json={"session_id": session_id},
        created_by=researcher_user.id,
    )
    db.add(target_object)
    await db.commit()

    original_commit = AsyncSession.commit

    async def fake_commit(self):
        if any(isinstance(item, ResearchObjectRelation) for item in self.new):
            raise IntegrityError("INSERT", {}, Exception("uq_research_object_relation"))
        await original_commit(self)

    monkeypatch.setattr(AsyncSession, "commit", fake_commit)

    response = await client.post(
        f"/api/v1/workflow-runs/{workflow_run.id}/save-memory",
        headers=researcher_headers,
        json={
            "type": "hypothesis",
            "title": "Workflow hypothesis",
            "content": "Workflow generated insight",
            "relation": {
                "enabled": True,
                "relation_type": "supports",
                "target_object_id": target_object.id,
            },
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Research relation already exists"


async def test_save_workflow_run_to_memory_rejects_cross_session_target(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
):
    session_id = await _create_session(client, researcher_headers)
    other_session_id = await _create_session(client, researcher_headers)
    workflow_run = await _create_workflow_run(
        db,
        session_id=session_id,
        user_id=researcher_user.id,
    )
    target_object = ResearchObject(
        type="discussion",
        title="Other session object",
        content_json={"session_id": other_session_id},
        created_by=researcher_user.id,
    )
    db.add(target_object)
    await db.commit()

    response = await client.post(
        f"/api/v1/workflow-runs/{workflow_run.id}/save-memory",
        headers=researcher_headers,
        json={
            "type": "discussion",
            "title": "Saved discussion",
            "content": "Workflow output text",
            "relation": {
                "enabled": True,
                "relation_type": "supports",
                "target_object_id": target_object.id,
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Target research object must belong to the same session"
