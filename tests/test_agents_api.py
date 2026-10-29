import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.agents import _build_agent_message_content
from app.models.agent_run import AgentRun
from app.models.message import Message
from app.models.research_object import ResearchObject, ResearchObjectRelation
from app.models.trace import ResearchTrace
from app.models.workflow_run import WorkflowRun
from app.schemas.agent import AgentRunResponse

pytestmark = pytest.mark.asyncio


async def test_agent_message_content_formats_raw_synthesis_json():
    content = _build_agent_message_content(
        "literature_synthesizer",
        {
            "overview": "",
            "key_points": [],
            "raw_synthesis": (
                '{"overview":"Concise overview","key_points":["Point A","Point B"],'
                '"contradictions":[],"gaps":["Gap A"]}'
            ),
        },
    )

    assert "Concise overview" in content
    assert "- Point A" in content
    assert "- Gap A" in content
    assert '"overview"' not in content


async def test_agent_message_content_hides_unparseable_raw_synthesis():
    content = _build_agent_message_content(
        "literature_synthesizer",
        {
            "overview": "",
            "key_points": [],
            "raw_synthesis": '{"overview":"cut off"',
        },
    )

    assert content == ""


async def _create_session(client: AsyncClient, headers: dict) -> str:
    response = await client.post(
        "/api/v1/sessions",
        json={"title": "Agent API Session"},
        headers=headers,
    )
    return response.json()["id"]


async def test_run_agent_persists_trace_and_returns_result(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
    monkeypatch,
):
    session_id = await _create_session(client, researcher_headers)

    async def fake_run_agent_definition(
        *,
        agent_name,
        source_ids,
        agent_input,
        db,
        llm_model,
        llm_api_base,
        llm_api_key,
        **_access_context,
    ):
        assert agent_name == "reviewer_assistant"
        assert source_ids == []
        assert agent_input == {"review_comments": "Address novelty concerns."}
        return {
            "output": {
                "agent": "reviewer_assistant",
                "response_strategy": ["Clarify contribution framing"],
            },
            "steps": [
                {
                    "name": "retrieve",
                    "status": "completed",
                    "summary": "retrieved 0 chunks",
                },
                {
                    "name": "format_output",
                    "status": "completed",
                    "summary": "prepared reviewer response draft",
                },
            ],
            "trace_payload": {
                "inputs": {"review_comments": "Address novelty concerns."},
                "retrieval": [],
                "citations": [],
                "summary_steps": [
                    "retrieved 0 chunks",
                    "prepared reviewer response draft",
                ],
            },
        }

    monkeypatch.setattr(
        "app.api.agents.run_agent_definition",
        fake_run_agent_definition,
    )

    response = await client.post(
        "/api/v1/agents/run",
        json={
            "session_id": session_id,
            "agent": "reviewer_assistant",
            "source_ids": [],
            "input": {"review_comments": "Address novelty concerns."},
        },
        headers=researcher_headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["agent_name"] == "reviewer_assistant"
    assert payload["status"] == "completed"
    assert payload["output"]["response_strategy"] == ["Clarify contribution framing"]
    assert payload["trace"]["inputs"] == {
        "review_comments": "Address novelty concerns."
    }

    agent_run = await db.scalar(select(AgentRun).where(AgentRun.id == payload["id"]))
    assert agent_run is not None
    assert agent_run.user_id == researcher_user.id
    assert agent_run.session_id == session_id

    trace = await db.scalar(
        select(ResearchTrace).where(ResearchTrace.agent_run_id == payload["id"])
    )
    assert trace is not None
    assert trace.session_id == session_id
    assert trace.user_id == researcher_user.id
    assert trace.inputs_json == {"review_comments": "Address novelty concerns."}


async def test_run_agent_persists_assistant_message_for_refresh(
    client: AsyncClient,
    researcher_headers: dict,
    db: AsyncSession,
    monkeypatch,
):
    session_id = await _create_session(client, researcher_headers)

    async def fake_run_agent_definition(**_kwargs):
        return {
            "output": {
                "summary": "Structured reviewer summary",
                "response_outline": ["Point-by-point response"],
            },
            "steps": [
                {
                    "name": "format_output",
                    "status": "completed",
                    "summary": "prepared reviewer response draft",
                },
            ],
            "trace_payload": {
                "inputs": {"review_comments": "Address novelty concerns."},
                "retrieval": [],
                "citations": [],
                "summary_steps": ["prepared reviewer response draft"],
            },
        }

    monkeypatch.setattr(
        "app.api.agents.run_agent_definition",
        fake_run_agent_definition,
    )

    response = await client.post(
        "/api/v1/agents/run",
        json={
            "session_id": session_id,
            "agent": "reviewer_assistant",
            "source_ids": [],
            "input": {"review_comments": "Address novelty concerns."},
        },
        headers=researcher_headers,
    )

    assert response.status_code == 201
    run_id = response.json()["id"]

    persisted_message = await db.scalar(
        select(Message)
        .where(Message.session_id == session_id, Message.role == "assistant")
        .order_by(Message.created_at.desc())
    )
    assert persisted_message is not None

    trace = await db.scalar(
        select(ResearchTrace).where(ResearchTrace.agent_run_id == run_id)
    )
    assert trace is not None
    assert trace.message_id == persisted_message.id

    messages_response = await client.get(
        f"/api/v1/sessions/{session_id}/messages",
        headers=researcher_headers,
    )
    assert messages_response.status_code == 200
    payload = messages_response.json()

    assistant_message = next(item for item in payload if item["id"] == persisted_message.id)
    assert assistant_message["role"] == "assistant"
    assert assistant_message["agent_run"]["id"] == run_id
    assert assistant_message["agent_run"]["agent_name"] == "reviewer_assistant"
    assert assistant_message["agent_run"]["output"]["summary"] == "Structured reviewer summary"


async def test_run_agent_creates_linked_workflow_run(
    client: AsyncClient,
    researcher_headers: dict,
    db: AsyncSession,
    monkeypatch,
):
    session_id = await _create_session(client, researcher_headers)

    async def fake_runner(**_kwargs):
        return {
            "output": {"agent": "reviewer_assistant", "summary": "Address concerns"},
            "steps": [
                {"name": "retrieve", "status": "completed", "summary": "retrieved 0 chunks"},
                {"name": "format_output", "status": "completed", "summary": "formatted"},
            ],
            "trace_payload": {
                "inputs": {"review_comments": "Please address novelty."},
                "retrieval": [],
                "citations": [],
                "summary_steps": ["retrieved 0 chunks", "formatted"],
            },
        }

    monkeypatch.setattr("app.api.agents.run_agent_definition", fake_runner)

    response = await client.post(
        "/api/v1/agents/run",
        json={
            "session_id": session_id,
            "agent": "reviewer_assistant",
            "source_ids": [],
            "input": {"review_comments": "Please address novelty."},
        },
        headers=researcher_headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["workflow_run_id"] is not None

    agent_run = await db.scalar(select(AgentRun).where(AgentRun.id == payload["id"]))
    assert agent_run is not None
    assert agent_run.workflow_run_id == payload["workflow_run_id"]


async def test_run_agent_preserves_legacy_step_names(
    client: AsyncClient,
    researcher_headers: dict,
    monkeypatch,
):
    session_id = await _create_session(client, researcher_headers)
    legacy_steps = [
        {"name": "retrieve", "status": "completed", "summary": "retrieved 0 chunks"},
        {
            "name": "synthesize",
            "status": "completed",
            "summary": "generated reviewer response draft",
        },
        {
            "name": "validate",
            "status": "completed",
            "summary": "validated reviewer response draft",
        },
        {
            "name": "format_output",
            "status": "completed",
            "summary": "prepared structured response",
        },
    ]

    async def fake_runner(**_kwargs):
        return {
            "output": {"agent": "reviewer_assistant", "summary": "Address concerns"},
            "steps": legacy_steps,
            "trace_payload": {
                "inputs": {"review_comments": "Please address novelty."},
                "retrieval": [],
                "citations": [],
                "summary_steps": [step["summary"] for step in legacy_steps],
            },
        }

    monkeypatch.setattr("app.api.agents.run_agent_definition", fake_runner)

    response = await client.post(
        "/api/v1/agents/run",
        json={
            "session_id": session_id,
            "agent": "reviewer_assistant",
            "source_ids": [],
            "input": {"review_comments": "Please address novelty."},
        },
        headers=researcher_headers,
    )

    assert response.status_code == 201
    assert response.json()["steps"] == legacy_steps


async def test_run_agent_failed_execution_links_workflow_run(
    client: AsyncClient,
    researcher_headers: dict,
    db: AsyncSession,
    monkeypatch,
):
    session_id = await _create_session(client, researcher_headers)

    async def failing_runner(**_kwargs):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr("app.api.agents.run_agent_definition", failing_runner)

    response = await client.post(
        "/api/v1/agents/run",
        json={
            "session_id": session_id,
            "agent": "reviewer_assistant",
            "source_ids": [],
            "input": {"review_comments": "Please address novelty."},
        },
        headers=researcher_headers,
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Agent execution failed."

    agent_run = await db.scalar(
        select(AgentRun)
        .where(AgentRun.session_id == session_id)
        .order_by(AgentRun.created_at.desc())
    )
    assert agent_run is not None
    assert agent_run.status == "failed"
    assert agent_run.workflow_run_id is not None

    workflow_run = await db.scalar(
        select(WorkflowRun).where(WorkflowRun.id == agent_run.workflow_run_id)
    )
    assert workflow_run is not None
    assert workflow_run.status == "failed"


async def test_run_agent_unknown_agent_returns_400(
    client,
    researcher_headers,
    db: AsyncSession,
):
    session_id = await _create_session(client, researcher_headers)
    response = await client.post(
        "/api/v1/agents/run",
        json={
            "session_id": session_id,
            "agent": "missing_agent",
            "source_ids": [],
            "input": {},
        },
        headers=researcher_headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown agent."

    agent_run = await db.scalar(
        select(AgentRun)
        .options(selectinload(AgentRun.traces))
        .where(
            AgentRun.session_id == session_id,
            AgentRun.agent_name == "missing_agent",
        )
    )
    assert agent_run is not None
    assert agent_run.status == "failed"
    assert agent_run.error_message == "Unknown agent"
    assert AgentRunResponse.model_validate(agent_run).agent_name == "missing_agent"


async def test_run_agent_requires_sources_linked_to_session(
    client: AsyncClient,
    researcher_headers: dict,
):
    session_id = await _create_session(client, researcher_headers)

    response = await client.post(
        "/api/v1/agents/run",
        json={
            "session_id": session_id,
            "agent": "literature_synthesizer",
            "source_ids": ["source-1", "source-2"],
            "input": {"query": "Compare the papers."},
        },
        headers=researcher_headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "All selected sources must be linked to the session."


async def test_get_agent_run_respects_user_isolation(
    client: AsyncClient,
    auth_headers: dict,
    researcher_headers: dict,
    monkeypatch,
):
    session_id = await _create_session(client, auth_headers)

    async def fake_run_agent_definition(**_kwargs):
        return {
            "output": {"agent": "reviewer_assistant"},
            "steps": [],
            "trace_payload": {
                "inputs": {"review_comments": "Admin only"},
                "retrieval": [],
                "citations": [],
                "summary_steps": [],
            },
        }

    monkeypatch.setattr(
        "app.api.agents.run_agent_definition",
        fake_run_agent_definition,
    )

    create_response = await client.post(
        "/api/v1/agents/run",
        json={
            "session_id": session_id,
            "agent": "reviewer_assistant",
            "source_ids": [],
            "input": {"review_comments": "Admin only"},
        },
        headers=auth_headers,
    )
    run_id = create_response.json()["id"]

    response = await client.get(
        f"/api/v1/agents/runs/{run_id}",
        headers=researcher_headers,
    )

    assert response.status_code == 404


async def test_save_agent_run_to_memory_creates_research_object(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
    monkeypatch,
):
    session_id = await _create_session(client, researcher_headers)

    async def fake_run_agent_definition(**_kwargs):
        return {
            "output": {
                "agent": "reviewer_assistant",
                "response_strategy": ["Turn reviewer comments into a hypothesis"],
            },
            "steps": [],
            "trace_payload": {
                "inputs": {"review_comments": "Address mechanism clarity."},
                "retrieval": [],
                "citations": [],
                "summary_steps": [],
            },
        }

    monkeypatch.setattr(
        "app.api.agents.run_agent_definition",
        fake_run_agent_definition,
    )

    run_response = await client.post(
        "/api/v1/agents/run",
        json={
            "session_id": session_id,
            "agent": "reviewer_assistant",
            "source_ids": [],
            "input": {"review_comments": "Address mechanism clarity."},
        },
        headers=researcher_headers,
    )
    assert run_response.status_code == 201
    run_id = run_response.json()["id"]

    response = await client.post(
        f"/api/v1/agents/runs/{run_id}/save-memory",
        json={
            "type": "hypothesis",
            "title": "Synthesized hypothesis",
            "content": "Agent output text",
            "relation": {"enabled": False},
        },
        headers=researcher_headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["research_object"]["type"] == "hypothesis"
    assert payload["research_object"]["title"] == "Synthesized hypothesis"
    assert payload["research_object"]["content"] == "Agent output text"
    assert payload["relation"] is None

    saved_object = await db.scalar(
        select(ResearchObject).where(ResearchObject.id == payload["research_object"]["id"])
    )
    assert saved_object is not None
    assert saved_object.created_by == researcher_user.id
    assert saved_object.content_json["session_id"] == session_id
    assert saved_object.content_json["origin"] == "agent_run"
    assert saved_object.content_json["agent_run_id"] == run_id


async def test_save_agent_run_to_memory_creates_relation_with_trace_evidence(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
    monkeypatch,
):
    session_id = await _create_session(client, researcher_headers)

    async def fake_run_agent_definition(**_kwargs):
        return {
            "output": {
                "overview": "This strengthens the saved hypothesis.",
            },
            "steps": [],
            "trace_payload": {
                "inputs": {"query": "What does this support?"},
                "retrieval": [],
                "citations": [
                    {
                        "source_id": "source-1",
                        "chunk_id": "chunk-1",
                        "snippet": "quoted support",
                    }
                ],
                "summary_steps": [],
            },
        }

    monkeypatch.setattr(
        "app.api.agents.run_agent_definition",
        fake_run_agent_definition,
    )

    run_response = await client.post(
        "/api/v1/agents/run",
        json={
            "session_id": session_id,
            "agent": "literature_synthesizer",
            "source_ids": ["source-1", "source-2"],
            "input": {"query": "What does this support?"},
        },
        headers=researcher_headers,
    )
    assert run_response.status_code == 400

    agent_run = AgentRun(
        session_id=session_id,
        user_id=researcher_user.id,
        agent_name="literature_synthesizer",
        status="completed",
        input_json={"query": "What does this support?"},
        output_json={"overview": "This strengthens the saved hypothesis."},
    )
    db.add(agent_run)
    await db.flush()

    trace = ResearchTrace(
        session_id=session_id,
        user_id=researcher_user.id,
        agent_run_id=agent_run.id,
        inputs_json={"query": "What does this support?", "source_ids": ["source-1"]},
        retrieval_json=[],
        citations_json=[
            {
                "source_id": "source-1",
                "chunk_id": "chunk-1",
                "snippet": "quoted support",
            }
        ],
        summary_steps_json=[],
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
        f"/api/v1/agents/runs/{agent_run.id}/save-memory",
        json={
            "type": "hypothesis",
            "title": "Synthesized hypothesis",
            "content": "Agent output text",
            "relation": {
                "enabled": True,
                "relation_type": "supports",
                "target_object_id": target_object.id,
                "note": "User confirmed the evidence chain.",
            },
        },
        headers=researcher_headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["relation"]["relation_type"] == "supports"
    assert payload["relation"]["target_object"]["id"] == target_object.id
    assert payload["relation"]["metadata_json"]["confidence"] == 0.8
    assert payload["relation"]["metadata_json"]["evidence"]["trace_id"] == trace.id
    assert payload["relation"]["metadata_json"]["evidence"]["citations"][0]["snippet"] == "quoted support"
    assert payload["relation"]["metadata_json"]["evidence"]["note"] == "User confirmed the evidence chain."


async def test_save_agent_run_to_memory_rejects_cross_session_target(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
):
    session_id = await _create_session(client, researcher_headers)
    other_session_id = await _create_session(client, researcher_headers)

    agent_run = AgentRun(
        session_id=session_id,
        user_id=researcher_user.id,
        agent_name="reviewer_assistant",
        status="completed",
        input_json={"review_comments": "Address mechanism clarity."},
        output_json={"overview": "Cross-session link should fail."},
    )
    target_object = ResearchObject(
        type="discussion",
        title="Other session object",
        content_json={"session_id": other_session_id},
        created_by=researcher_user.id,
    )
    db.add_all([agent_run, target_object])
    await db.commit()

    response = await client.post(
        f"/api/v1/agents/runs/{agent_run.id}/save-memory",
        json={
            "type": "discussion",
            "title": "Saved discussion",
            "content": "Agent output text",
            "relation": {
                "enabled": True,
                "relation_type": "supports",
                "target_object_id": target_object.id,
            },
        },
        headers=researcher_headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Target research object must belong to the same session"


async def test_save_agent_run_to_memory_without_trace_keeps_empty_relation_evidence(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
):
    session_id = await _create_session(client, researcher_headers)

    agent_run = AgentRun(
        session_id=session_id,
        user_id=researcher_user.id,
        agent_name="reviewer_assistant",
        status="completed",
        input_json={"review_comments": "Address mechanism clarity."},
        output_json={"overview": "No persisted trace for this run."},
    )
    target_object = ResearchObject(
        type="discussion",
        title="Existing object",
        content_json={"session_id": session_id},
        created_by=researcher_user.id,
    )
    db.add_all([agent_run, target_object])
    await db.commit()

    response = await client.post(
        f"/api/v1/agents/runs/{agent_run.id}/save-memory",
        json={
            "type": "discussion",
            "title": "Saved without trace",
            "content": "Agent output text",
            "relation": {
                "enabled": True,
                "relation_type": "supports",
                "target_object_id": target_object.id,
            },
        },
        headers=researcher_headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["relation"]["metadata_json"]["confidence"] == 0.8
    assert payload["relation"]["metadata_json"]["evidence"] == {
        "trace_id": None,
        "citations": [],
        "note": None,
    }
