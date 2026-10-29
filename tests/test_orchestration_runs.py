from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.models.orchestration_run import OrchestrationRun
from app.models.access_policy import AccessPolicy
from app.models.asset_revision import AssetRevision
from app.models.project import Project, ResearcherProject
from app.models.session import Session
from app.models.source import Chunk, Source
from app.models.task_definition import TaskDefinitionRecord
from app.models.user import User, Workspace
from app.core.governance import Capability
from app.services.orchestration_service import (
    InvalidOrchestrationTransitionError,
    OrchestrationSessionNotFoundError,
    build_orchestration_context,
    create_orchestration_run,
    transition_orchestration_run,
)
from app.services.research_asset_service import materialize_source_asset
from app.services.research_context import (
    ResearchContextChunk,
    ResearchExecutionContext,
    build_research_execution_context,
    collect_project_source_ids,
)

pytestmark = pytest.mark.asyncio


async def _create_project(
    client: AsyncClient,
    headers: dict[str, str],
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
    headers: dict[str, str],
    *,
    task_id: str,
    project_ids: list[str] | None = None,
    is_enabled: bool = True,
) -> None:
    response = await client.post(
        "/api/v1/admin/tasks",
        headers=headers,
        json={
            "id": task_id,
            "version": 1,
            "name": "Session Task",
            "description": "Task used for session creation tests.",
            "workflow_id": "reviewer_assistant",
            "input_schema": {"type": "object"},
            "starter_prompts": [],
            "project_context_policy": {"mode": "project_optional"},
            "result_presentation": {"type": "markdown"},
            "is_enabled": is_enabled,
            "project_ids": project_ids or [],
        },
    )
    assert response.status_code == 201


async def test_create_session_persists_task_identity(
    client: AsyncClient,
    researcher_headers: dict[str, str],
    auth_headers: dict[str, str],
):
    project_id = await _create_project(
        client,
        researcher_headers,
        name="Task Project",
    )
    await _create_task_definition(
        client,
        auth_headers,
        task_id="session-task",
        project_ids=[project_id],
    )

    response = await client.post(
        "/api/v1/sessions",
        json={
            "project_id": project_id,
            "task_id": "session-task",
            "title": "Q&A",
        },
        headers=researcher_headers,
    )

    assert response.status_code == 201
    assert response.json()["task_id"] == "session-task"
    assert response.json()["conversation_summary"] is None


async def test_create_session_rejects_too_long_task_id(
    client: AsyncClient,
    researcher_headers: dict[str, str],
):
    response = await client.post(
        "/api/v1/sessions",
        json={"task_id": "x" * 101},
        headers=researcher_headers,
    )

    assert response.status_code == 422


async def test_create_session_rejects_unknown_task(
    client: AsyncClient,
    researcher_headers: dict[str, str],
):
    response = await client.post(
        "/api/v1/sessions",
        json={"task_id": "unknown-task"},
        headers=researcher_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


async def test_create_session_rejects_disabled_task(
    client: AsyncClient,
    researcher_headers: dict[str, str],
    auth_headers: dict[str, str],
):
    await _create_task_definition(
        client,
        auth_headers,
        task_id="disabled-session-task",
        is_enabled=False,
    )

    response = await client.post(
        "/api/v1/sessions",
        json={"task_id": "disabled-session-task"},
        headers=researcher_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


async def test_create_session_rejects_task_outside_project_scope(
    client: AsyncClient,
    researcher_headers: dict[str, str],
    auth_headers: dict[str, str],
):
    task_project_id = await _create_project(
        client,
        researcher_headers,
        name="Task Scope Project",
    )
    session_project_id = await _create_project(
        client,
        researcher_headers,
        name="Session Scope Project",
    )
    await _create_task_definition(
        client,
        auth_headers,
        task_id="scoped-session-task",
        project_ids=[task_project_id],
    )

    response = await client.post(
        "/api/v1/sessions",
        json={
            "project_id": session_project_id,
            "task_id": "scoped-session-task",
        },
        headers=researcher_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


async def test_orchestration_run_persists_snapshots(
    db: AsyncSession,
    researcher_user: User,
):
    workspace = await db.scalar(
        select(Workspace).where(Workspace.researcher_id == researcher_user.id)
    )
    session = Session(workspace_id=workspace.id, title="Orchestration Session")
    db.add(session)
    await db.flush()

    run = OrchestrationRun(
        session_id=session.id,
        task_id="literature-review",
        turn_index=1,
        status="planning",
        capability_snapshot={"skills": ["rag-retrieve"]},
        context_manifest={"chunk_ids": ["chunk-1"]},
        output_contract_snapshot={"artifact_type": "answer"},
        created_by=researcher_user.id,
    )
    db.add(run)
    await db.commit()

    reloaded = await db.scalar(
        select(OrchestrationRun).where(OrchestrationRun.id == run.id)
    )

    assert reloaded is not None
    assert reloaded.created_by == researcher_user.id
    assert reloaded.status == "planning"
    assert reloaded.capability_snapshot == {"skills": ["rag-retrieve"]}
    assert reloaded.context_manifest == {"chunk_ids": ["chunk-1"]}
    assert reloaded.output_contract_snapshot == {"artifact_type": "answer"}


async def test_build_orchestration_context_uses_authorized_ids_without_raw_content(
    db: AsyncSession,
    researcher_user: User,
):
    workspace = await db.scalar(
        select(Workspace).where(Workspace.researcher_id == researcher_user.id)
    )
    project = Project(name="Context Project", description=None)
    db.add(project)
    await db.flush()

    session = Session(
        workspace_id=workspace.id,
        project_id=project.id,
        title="Context Session",
        task_id="literature-review",
    )
    source = Source(
        type="file",
        name="paper.pdf",
        owner_id=researcher_user.id,
        content_path="/private/research/raw-paper.pdf",
    )
    db.add_all([session, source])
    await db.flush()
    db.add(
        Chunk(
            source_id=source.id,
            chunk_index=0,
            text="raw_pdf_path=/private/research/raw-paper.pdf",
        )
    )
    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=researcher_user.id,
        origin_project_id=project.id,
        origin_session_id=None,
        visibility_scope="project",
        link_type="source",
    )
    revision = await db.get(AssetRevision, asset.current_revision_id)
    assert revision is not None
    db.add(
        ResearcherProject(
            project_id=project.id,
            researcher_id=researcher_user.id,
            role="owner",
        )
    )
    db.add(
        AccessPolicy(
            research_asset_id=asset.id,
            asset_revision_id=revision.id,
            subject_type="user",
            subject_id=researcher_user.id,
            capabilities_json=[Capability.CONTENT_USE_IN_AGENT],
            required_project_id=project.id,
            valid_until=datetime.now(UTC) + timedelta(days=30),
            created_by=researcher_user.id,
        )
    )
    await db.commit()

    assert await collect_project_source_ids(
        db=db,
        project_id=project.id,
        user=researcher_user,
    ) == [source.id]

    context, manifest = await build_orchestration_context(
        db=db,
        session_id=session.id,
        user=researcher_user,
    )

    assert [chunk.chunk_id for chunk in context.chunks]
    assert manifest["source_ids"] == [source.id]
    assert manifest["chunk_ids"] == [context.chunks[0].chunk_id]
    assert "raw_pdf_path" not in str(manifest)
    assert "/private/research/raw-paper.pdf" not in str(manifest)


@pytest.mark.parametrize("selection", [None, [], ["source-group"]])
async def test_build_orchestration_context_expands_selected_groups_without_visibility_filter(
    db: AsyncSession,
    researcher_user: User,
    monkeypatch: pytest.MonkeyPatch,
    selection: list[str] | None,
):
    workspace = await db.scalar(
        select(Workspace).where(Workspace.researcher_id == researcher_user.id)
    )
    session = Session(workspace_id=workspace.id, title="Selected Sources")
    db.add(session)
    await db.flush()
    captured_user_id: str | None = "not-called"

    async def fake_collect_project_source_ids(**kwargs):
        return ["project-source"]

    async def fake_expand_source_ids(source_ids, db, user_id=None):
        nonlocal captured_user_id
        captured_user_id = user_id
        return ["project-source"] if source_ids else []

    async def fake_build_context(**kwargs):
        assert kwargs["source_ids"] == ([] if selection == [] else ["project-source"])
        return ResearchExecutionContext()

    monkeypatch.setattr(
        "app.services.orchestration_service.collect_project_source_ids",
        fake_collect_project_source_ids,
    )
    monkeypatch.setattr(
        "app.services.orchestration_service.expand_source_ids_for_rag",
        fake_expand_source_ids,
    )
    monkeypatch.setattr(
        "app.services.orchestration_service.build_research_execution_context",
        fake_build_context,
    )

    _, manifest = await build_orchestration_context(
        db=db,
        session_id=session.id,
        user=researcher_user,
        source_ids=selection,
    )

    assert manifest["source_ids"] == ([] if selection == [] else ["project-source"])
    if selection is not None:
        assert captured_user_id is None


async def test_evidence_question_adds_result_sections_to_retrieval_context(
    db: AsyncSession,
    researcher_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    workspace = await db.scalar(
        select(Workspace).where(Workspace.researcher_id == researcher_user.id)
    )
    project = Project(name="Evidence Project", description=None)
    session = Session(
        workspace_id=workspace.id,
        project_id=project.id,
        title="Evidence Session",
        task_id="project-qa",
    )
    source = Source(
        type="file",
        name="Evidence paper.pdf",
        owner_id=researcher_user.id,
        content_path="/private/research/evidence-paper.pdf",
    )
    db.add_all([project, session, source])
    await db.flush()
    method_chunk = Chunk(
        source_id=source.id,
        chunk_index=1,
        text="## 2.1. Cell culture\nCell lines were maintained in culture.",
    )
    result_chunk = Chunk(
        source_id=source.id,
        chunk_index=2,
        text="## 3.1. Results\nThe intervention reduced infection in the cell model.",
    )
    db.add_all([method_chunk, result_chunk])
    await db.flush()

    async def always_authorized(**kwargs):
        return True

    async def retrieve_only_method(*args, **kwargs):
        return [
            {
                "source_id": source.id,
                "chunk_id": method_chunk.id,
                "text": method_chunk.text,
                "score": 0.9,
            }
        ]

    monkeypatch.setattr(
        "app.services.research_context.can_user_use_source_in_agent",
        always_authorized,
    )
    monkeypatch.setattr(
        "app.services.research_context._rag_chunks",
        retrieve_only_method,
    )

    context = await build_research_execution_context(
        db=db,
        session_id=session.id,
        user_id=researcher_user.id,
        source_ids=[source.id],
        query="What experimental models, results, and mechanisms does this paper show?",
        max_chunks=4,
    )

    assert {chunk.chunk_id for chunk in context.chunks} == {
        method_chunk.id,
        result_chunk.id,
    }


async def test_transition_orchestration_run_rejects_terminal_transition(
    db: AsyncSession,
    researcher_user: User,
):
    workspace = await db.scalar(
        select(Workspace).where(Workspace.researcher_id == researcher_user.id)
    )
    session = Session(workspace_id=workspace.id, title="Terminal Run Session")
    db.add(session)
    await db.flush()
    run = OrchestrationRun(
        session_id=session.id,
        task_id="literature-review",
        turn_index=1,
        status="completed",
        created_by=researcher_user.id,
    )
    db.add(run)
    await db.commit()

    with pytest.raises(InvalidOrchestrationTransitionError):
        await transition_orchestration_run(
            db=db,
            run_id=run.id,
            user=researcher_user,
            target_status="running",
        )


async def test_create_orchestration_run_uses_session_task_and_persists_snapshots(
    db: AsyncSession,
    researcher_user: User,
):
    workspace = await db.scalar(
        select(Workspace).where(Workspace.researcher_id == researcher_user.id)
    )
    db.add(
        TaskDefinitionRecord(
            id="orchestration-task",
            name="Orchestration Task",
            description="Task for orchestration service tests.",
            workflow_id="reviewer_assistant",
            input_schema={"type": "object"},
            starter_prompts=[],
            project_context_policy={"mode": "project_optional"},
            result_presentation={"type": "markdown"},
            is_enabled=True,
            project_ids=[],
        )
    )
    session = Session(
        workspace_id=workspace.id,
        title="Create Run Session",
        task_id="orchestration-task",
    )
    db.add(session)
    await db.commit()

    run = await create_orchestration_run(
        db=db,
        session_id=session.id,
        user=researcher_user,
        capability_snapshot={"skills": ["rag-retrieve"]},
        output_contract_snapshot={"artifact_type": "answer"},
    )
    await db.commit()

    reloaded = await db.get(OrchestrationRun, run.id)
    assert reloaded is not None
    assert reloaded.task_id == session.task_id
    assert reloaded.turn_index == 1
    assert reloaded.status == "planning"
    assert reloaded.capability_snapshot == {"skills": ["rag-retrieve"]}
    assert reloaded.output_contract_snapshot == {"artifact_type": "answer"}

    with pytest.raises(ValueError, match="does not match session task"):
        await create_orchestration_run(
            db=db,
            session_id=session.id,
            user=researcher_user,
            task_id="another-task",
        )


async def test_create_orchestration_run_assigns_next_turn_index(
    db: AsyncSession,
    researcher_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    workspace = await db.scalar(
        select(Workspace).where(Workspace.researcher_id == researcher_user.id)
    )
    db.add(
        TaskDefinitionRecord(
            id="turn-index-task",
            name="Turn Index Task",
            description="Task for turn index allocation tests.",
            workflow_id="reviewer_assistant",
            input_schema={"type": "object"},
            starter_prompts=[],
            project_context_policy={"mode": "project_optional"},
            result_presentation={"type": "markdown"},
            is_enabled=True,
            project_ids=[],
        )
    )
    session = Session(
        workspace_id=workspace.id,
        title="Turn Index Session",
        task_id="turn-index-task",
    )
    db.add(session)
    await db.commit()

    db.add(
        OrchestrationRun(
            session_id=session.id,
            task_id=session.task_id,
            turn_index=1,
            status="planning",
            created_by=researcher_user.id,
        )
    )
    await db.commit()
    original_scalar = db.scalar
    stale_max_reads = 0

    async def scalar_with_stale_first_max(statement, *args, **kwargs):
        nonlocal stale_max_reads
        if "max(orchestration_runs.turn_index)" in str(statement):
            stale_max_reads += 1
            if stale_max_reads == 1:
                return 0
        return await original_scalar(statement, *args, **kwargs)

    monkeypatch.setattr(db, "scalar", scalar_with_stale_first_max)
    run = await create_orchestration_run(
        db=db,
        session_id=session.id,
        user=researcher_user,
    )

    assert stale_max_reads == 2
    assert run.turn_index == 2


async def test_transition_orchestration_run_updates_persisted_status_once(
    db: AsyncSession,
    researcher_user: User,
):
    workspace = await db.scalar(
        select(Workspace).where(Workspace.researcher_id == researcher_user.id)
    )
    session = Session(workspace_id=workspace.id, title="Transition Run Session")
    db.add(session)
    await db.flush()
    run = OrchestrationRun(
        session_id=session.id,
        task_id="literature-review",
        turn_index=1,
        status="planning",
        created_by=researcher_user.id,
    )
    db.add(run)
    await db.commit()

    transitioned = await transition_orchestration_run(
        db=db,
        run_id=run.id,
        user=researcher_user,
        target_status="running",
    )
    await db.commit()

    assert transitioned.status == "running"
    assert (await db.get(OrchestrationRun, run.id)).status == "running"
    with pytest.raises(InvalidOrchestrationTransitionError):
        await transition_orchestration_run(
            db=db,
            run_id=run.id,
            user=researcher_user,
            target_status="running",
        )


async def test_transition_orchestration_run_rejects_cross_workspace_user(
    db: AsyncSession,
    researcher_user: User,
    admin_user: User,
):
    workspace = await db.scalar(
        select(Workspace).where(Workspace.researcher_id == researcher_user.id)
    )
    session = Session(workspace_id=workspace.id, title="Private Transition Session")
    db.add(session)
    await db.flush()
    run = OrchestrationRun(
        session_id=session.id,
        task_id="literature-review",
        turn_index=1,
        status="planning",
        created_by=researcher_user.id,
    )
    db.add(run)
    await db.commit()

    with pytest.raises(OrchestrationSessionNotFoundError):
        await transition_orchestration_run(
            db=db,
            run_id=run.id,
            user=admin_user,
            target_status="running",
        )

    assert (await db.get(OrchestrationRun, run.id)).status == "planning"


async def test_project_qa_run_persists_final_assistant_message(
    client: AsyncClient,
    researcher_headers: dict[str, str],
    auth_headers: dict[str, str],
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project_id = await _create_project(client, researcher_headers, name="Q&A Project")
    session_response = await client.post(
        "/api/v1/sessions",
        headers=researcher_headers,
        json={"project_id": project_id, "task_id": "project-qa", "title": "Q&A"},
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]
    captured_prompt = ""

    async def fake_run_codex_runtime(*, prompt, db, cwd=None, sandbox=None):
        nonlocal captured_prompt
        captured_prompt = prompt
        return {"status": "completed", "content": "Project answer."}

    monkeypatch.setattr(
        "app.services.orchestration_service.run_codex_runtime",
        fake_run_codex_runtime,
    )

    response = await client.post(
        f"/api/v1/sessions/{session_id}/orchestration-runs/project-qa",
        headers=researcher_headers,
        json={"goal": "What evidence supports the main finding?"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["task_id"] == "project-qa"
    assert payload["final_message_id"]
    assert "What evidence supports" in captured_prompt
    assert "Never ask the user to paste authorized source material" in captured_prompt
    message = await db.get(Message, payload["final_message_id"])
    assert message is not None
    assert message.role == "assistant"
    assert message.content == "Project answer."

    listed = await client.get(
        f"/api/v1/sessions/{session_id}/orchestration-runs",
        headers=researcher_headers,
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [payload["id"]]

    fetched = await client.get(
        f"/api/v1/orchestration-runs/{payload['id']}",
        headers=researcher_headers,
    )
    assert fetched.status_code == 200
    assert fetched.json()["final_message_id"] == payload["final_message_id"]


async def test_project_qa_runs_from_a_different_project_session_task(
    client: AsyncClient,
    researcher_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
):
    project_id = await _create_project(client, researcher_headers, name="Mixed Task Project")
    session_response = await client.post(
        "/api/v1/sessions",
        headers=researcher_headers,
        json={"project_id": project_id, "task_id": "core-ideas", "title": "Core ideas"},
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    async def fake_run_codex_runtime(*, prompt, db, cwd=None, sandbox=None):
        return {"status": "completed", "content": "Project answer."}

    monkeypatch.setattr(
        "app.services.orchestration_service.run_codex_runtime",
        fake_run_codex_runtime,
    )

    response = await client.post(
        f"/api/v1/sessions/{session_id}/orchestration-runs/project-qa",
        headers=researcher_headers,
        json={"goal": "What does the project show?"},
    )

    assert response.status_code == 201
    assert response.json()["task_id"] == "project-qa"


async def test_project_qa_run_persists_the_query_retrieval_manifest(
    client: AsyncClient,
    researcher_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
):
    project_id = await _create_project(client, researcher_headers, name="Manifest Project")
    session_response = await client.post(
        "/api/v1/sessions",
        headers=researcher_headers,
        json={"project_id": project_id, "task_id": "project-qa", "title": "Q&A"},
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    context = ResearchExecutionContext(
        chunks=[
            ResearchContextChunk(
                source_id="source-1",
                source_name="Authorized full text.pdf",
                chunk_id="query-result-1",
                text="A result section excerpt.",
            )
        ]
    )
    query_manifest = {
        "source_ids": ["source-1"],
        "chunk_ids": ["query-result-1"],
        "memory_ids": [],
        "limits": {},
    }
    captured_source_ids: list[str] | None = None

    async def fake_build_orchestration_context(*, query=None, **kwargs):
        nonlocal captured_source_ids
        captured_source_ids = kwargs.get("source_ids")
        if query:
            return context, query_manifest
        return ResearchExecutionContext(), {
            "source_ids": [],
            "chunk_ids": [],
            "memory_ids": [],
            "limits": {},
        }

    async def fake_run_codex_runtime(*, prompt, db, cwd=None, sandbox=None):
        return {"status": "completed", "content": "Project answer."}

    monkeypatch.setattr(
        "app.services.orchestration_service.build_orchestration_context",
        fake_build_orchestration_context,
    )
    monkeypatch.setattr(
        "app.services.orchestration_service.run_codex_runtime",
        fake_run_codex_runtime,
    )

    response = await client.post(
        f"/api/v1/sessions/{session_id}/orchestration-runs/project-qa",
        headers=researcher_headers,
        json={
            "goal": "What does this paper show?",
            "source_ids": ["source-1"],
        },
    )

    assert response.status_code == 201
    assert response.json()["context_manifest"] == query_manifest
    assert captured_source_ids == ["source-1"]


async def test_project_qa_run_marks_run_failed_when_codex_errors(
    client: AsyncClient,
    researcher_headers: dict[str, str],
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
):
    project_id = await _create_project(client, researcher_headers, name="Q&A failure")
    session_response = await client.post(
        "/api/v1/sessions",
        headers=researcher_headers,
        json={
            "project_id": project_id,
            "task_id": "project-qa",
            "title": "Q&A failure",
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    async def failing_run_codex_runtime(*, prompt, db, cwd=None, sandbox=None):
        raise RuntimeError("runtime unavailable")

    monkeypatch.setattr(
        "app.services.orchestration_service.run_codex_runtime",
        failing_run_codex_runtime,
    )

    response = await client.post(
        f"/api/v1/sessions/{session_id}/orchestration-runs/project-qa",
        headers=researcher_headers,
        json={"goal": "Explain the evidence."},
    )

    assert response.status_code == 502
    listed = await client.get(
        f"/api/v1/sessions/{session_id}/orchestration-runs",
        headers=researcher_headers,
    )
    assert listed.status_code == 200
    assert listed.json()[0]["status"] == "failed"
    assert listed.json()[0]["error_code"] == "codex_runtime_failed"
