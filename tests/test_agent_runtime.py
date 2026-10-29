import asyncio
from datetime import UTC, datetime
import importlib
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun
from app.core.database import Base
from app.models.session import Session
from app.models.trace import ResearchTrace
from app.models.user import User, Workspace
from app.schemas.agent import AgentRunCreateRequest, AgentRunResponse
from app.services import llm_service
from app.services.agent_runtime import (
    DuplicateAgentRegistrationError,
    UnknownAgentError,
    register_agent_definition,
    run_agent_definition,
)
from app.services.agents.base import AgentDefinition, build_agent_step_summary, build_step_record
from app.services.agents import literature_synthesizer, reviewer_assistant
from app.services.trace_service import build_agent_trace_payload


@pytest.mark.asyncio
async def test_deleting_agent_run_removes_linked_research_traces(db: AsyncSession):
    user = User(username="agent-user", hashed_password="hashed", role="researcher")
    db.add(user)
    await db.flush()

    workspace = Workspace(researcher_id=user.id)
    db.add(workspace)
    await db.flush()

    session = Session(workspace_id=workspace.id, title="Agent Session")
    db.add(session)
    await db.flush()

    agent_run = AgentRun(
        session_id=session.id,
        user_id=user.id,
        agent_name="literature_synthesizer",
    )
    db.add(agent_run)
    await db.flush()

    trace = ResearchTrace(
        session_id=session.id,
        user_id=user.id,
        agent_run_id=agent_run.id,
        inputs_json={"query": "compare"},
        retrieval_json=[],
        citations_json=[],
        summary_steps_json=[],
    )
    db.add(trace)
    await db.commit()

    await db.refresh(agent_run)
    await db.delete(agent_run)
    await db.commit()

    remaining_trace = await db.scalar(
        select(ResearchTrace).where(ResearchTrace.id == trace.id)
    )

    assert remaining_trace is None


@pytest.mark.asyncio
async def test_agent_run_table_is_registered(db: AsyncSession):
    result = await db.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    table_names = {name for (name,) in result.all()}

    assert "agent_runs" in Base.metadata.tables
    assert "agent_runs" in table_names

    research_traces_table = Base.metadata.tables["research_traces"]
    assert "agent_run_id" in research_traces_table.c

    foreign_keys = {fk.column.table.name for fk in research_traces_table.c.agent_run_id.foreign_keys}
    assert foreign_keys == {"agent_runs"}


def test_literature_synthesizer_requires_two_sources():
    with pytest.raises(ValidationError):
        AgentRunCreateRequest(
            session_id="session-1",
            agent="literature_synthesizer",
            source_ids=["source-1"],
            input={"query": "compare these"},
        )


def test_reviewer_assistant_allows_empty_source_selection():
    request = AgentRunCreateRequest(
        session_id="session-1",
        agent="reviewer_assistant",
        source_ids=[],
        input={"review_comments": "Please address novelty concerns."},
    )

    assert request.agent == "reviewer_assistant"
    assert request.source_ids == []


@pytest.mark.parametrize("bad_query", ["", "   ", None])
def test_literature_synthesizer_requires_non_empty_query(bad_query):
    with pytest.raises(ValidationError):
        AgentRunCreateRequest(
            session_id="session-1",
            agent="literature_synthesizer",
            source_ids=["source-1", "source-2"],
            input={"query": bad_query},
        )


@pytest.mark.parametrize("bad_review_comments", ["", "   ", None])
def test_reviewer_assistant_requires_non_empty_review_comments(bad_review_comments):
    with pytest.raises(ValidationError):
        AgentRunCreateRequest(
            session_id="session-1",
            agent="reviewer_assistant",
            source_ids=[],
            input={"review_comments": bad_review_comments},
        )


def test_agent_run_response_maps_json_fields():
    response = AgentRunResponse.model_validate(
        {
            "id": "run-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "workflow_run_id": "workflow-run-1",
            "agent_name": "literature_synthesizer",
            "status": "completed",
            "input_json": {"query": "What changed?"},
            "steps_json": [
                {"name": "retrieve", "status": "completed", "summary": "retrieved 2 chunks"}
            ],
            "output_json": {"overview": "summary"},
            "trace": {
                "inputs": {"query": "What changed?"},
                "retrieval": [],
                "citations": [],
                "summary_steps": ["retrieve", "summarize"],
            },
            "created_at": datetime(2026, 7, 7, tzinfo=UTC),
            "updated_at": datetime(2026, 7, 7, tzinfo=UTC),
        }
    )

    assert response.input == {"query": "What changed?"}
    assert response.workflow_run_id == "workflow-run-1"
    assert response.steps[0].name == "retrieve"
    assert response.output["overview"] == "summary"
    assert response.trace is not None
    assert response.trace.summary_steps == ["retrieve", "summarize"]


def test_agent_run_response_maps_latest_trace_from_orm_style_traces():
    older_trace = SimpleNamespace(
        inputs_json={"query": "older"},
        retrieval_json=[{"chunk_id": "c1"}],
        citations_json=[],
        summary_steps_json=["older"],
        created_at=datetime(2026, 7, 7, 0, 0, 1, tzinfo=UTC),
        id="trace-1",
    )
    newer_trace = SimpleNamespace(
        inputs_json={"query": "newer"},
        retrieval_json=[{"chunk_id": "c2"}],
        citations_json=[{"chunk_id": "c2"}],
        summary_steps_json=["newer"],
        created_at=datetime(2026, 7, 7, 0, 0, 2, tzinfo=UTC),
        id="trace-2",
    )

    response = AgentRunResponse.model_validate(
        {
            "id": "run-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "agent_name": "literature_synthesizer",
            "status": "completed",
            "input_json": {"query": "What changed?"},
            "steps_json": [],
            "output_json": {"overview": "summary"},
            "traces": [older_trace, newer_trace],
        }
    )

    assert response.trace is not None
    assert response.trace.inputs == {"query": "newer"}
    assert response.trace.retrieval == [{"chunk_id": "c2"}]
    assert response.trace.summary_steps == ["newer"]


def test_build_agent_trace_payload_uses_minimal_retrieved_chunk_fields():
    payload = build_agent_trace_payload(
        inputs={"query": "compare"},
        retrieved_chunks=[
            {
                "source_id": "src-1",
                "chunk_id": "chunk-1",
                "text": "A   detailed\nsnippet",
            }
        ],
        summary_steps=["retrieve"],
        citations=[],
    )

    assert payload["retrieval"] == [
        {
            "source_id": "src-1",
            "chunk_id": "chunk-1",
            "score": None,
            "snippet": "A detailed snippet",
        }
    ]


def test_build_step_record_defaults_to_completed_status():
    step = build_step_record("retrieve", "retrieved 3 chunks")

    assert step == {
        "name": "retrieve",
        "status": "completed",
        "summary": "retrieved 3 chunks",
    }


def test_build_agent_step_summary_uses_chinese_for_zh_cn():
    assert build_agent_step_summary("retrieve", locale="zh-CN", chunk_count=3) == "检索到 3 个片段"
    assert build_agent_step_summary("synthesize_literature", locale="zh-CN") == "已生成文献综合草稿"
    assert build_agent_step_summary("format_output", locale="zh-CN") == "已整理结构化输出"


@pytest.mark.asyncio
async def test_run_agent_definition_invokes_registered_runner(monkeypatch):
    captured: dict = {}

    async def fake_runner(
        *,
        source_ids,
        agent_input,
        db,
        llm_model,
        llm_api_base,
        llm_api_key,
        **_access_context,
    ):
        captured.update(
            {
                "source_ids": source_ids,
                "agent_input": agent_input,
                "db": db,
                "llm_model": llm_model,
                "llm_api_base": llm_api_base,
                "llm_api_key": llm_api_key,
            }
        )
        return {
            "output": {"overview": "done"},
            "steps": [build_step_record("retrieve", "retrieved 1 chunk")],
            "trace_payload": {
                "inputs": {"query": "hello"},
                "retrieval": [],
                "citations": [],
                "summary_steps": ["retrieve"],
            },
        }

    monkeypatch.setattr(
        "app.services.agent_runtime.AGENT_REGISTRY",
        {"fake-agent": AgentDefinition(name="fake-agent", runner=fake_runner)},
    )

    result = await run_agent_definition(
        agent_name="fake-agent",
        source_ids=["source-1"],
        agent_input={"query": "hello"},
        db=None,
        llm_model="model-x",
        llm_api_base="http://localhost:4000",
        llm_api_key="key-x",
    )

    assert result["output"]["overview"] == "done"
    assert result["steps"][0]["name"] == "retrieve"
    assert captured["source_ids"] == ["source-1"]
    assert captured["agent_input"] == {"query": "hello"}
    assert captured["llm_model"] == "model-x"


@pytest.mark.asyncio
async def test_literature_synthesizer_happy_path_and_step_order(monkeypatch):
    retrieved_chunks = [
        {
            "source_id": "source-1",
            "chunk_id": "chunk-1",
            "text": "Finding A",
            "score": 0.9,
        },
        {
            "source_id": "source-2",
            "chunk_id": "chunk-2",
            "text": "Finding B",
            "score": 0.8,
        },
    ]

    async def fake_retrieve_chunks(query, source_ids, db, mode, top_k=5, **_kwargs):
        assert query == "Compare the findings"
        assert source_ids == ["source-1", "source-2"]
        assert mode == "rag"
        assert top_k == 5
        return retrieved_chunks

    responses = iter(
        [
            '{"overview":"Combined view","key_points":["A","B"]}',
            '{"is_valid": true, "notes": ["grounded"]}',
        ]
    )

    async def fake_complete_llm_response(messages, model=None, api_base=None, api_key=None, max_tokens=None):
        assert model == "model-x"
        assert api_base == "http://localhost:4000"
        assert api_key == "key-x"
        assert messages[0]["role"] == "system"
        return next(responses)

    monkeypatch.setattr(literature_synthesizer, "retrieve_chunks", fake_retrieve_chunks)
    monkeypatch.setattr(
        literature_synthesizer,
        "complete_llm_response",
        fake_complete_llm_response,
    )

    result = await run_agent_definition(
        agent_name="literature_synthesizer",
        source_ids=["source-1", "source-2"],
        agent_input={"query": "Compare the findings"},
        db=None,
        llm_model="model-x",
        llm_api_base="http://localhost:4000",
        llm_api_key="key-x",
    )

    assert [step["name"] for step in result["steps"]] == [
        "retrieve",
        "synthesize",
        "validate",
        "format_output",
    ]
    assert result["output"]["agent"] == "literature_synthesizer"
    assert result["output"]["query"] == "Compare the findings"
    assert result["output"]["overview"] == "Combined view"
    assert result["output"]["validation"]["is_valid"] is True
    assert result["trace_payload"]["summary_steps"] == [
        "retrieved 2 chunks",
        "generated synthesis draft",
        "validated synthesis draft",
        "prepared structured response",
    ]
    assert len(result["trace_payload"]["citations"]) == 2


@pytest.mark.asyncio
async def test_literature_synthesizer_retries_truncated_synthesis_json(monkeypatch):
    async def fake_retrieve_chunks(query, source_ids, db, mode, top_k=5, **_kwargs):
        return []

    responses = iter(
        [
            '{"overview":"Partial response","key_points":["A"',
            '{"overview":"Recovered overview","key_points":["Recovered point"],"contradictions":[],"gaps":[]}',
            '{"is_valid": true, "notes": ["grounded"]}',
        ]
    )
    calls: list[list[dict]] = []

    async def fake_complete_llm_response(messages, model=None, api_base=None, api_key=None, max_tokens=None):
        calls.append(messages)
        return next(responses)

    monkeypatch.setattr(literature_synthesizer, "retrieve_chunks", fake_retrieve_chunks)
    monkeypatch.setattr(
        literature_synthesizer,
        "complete_llm_response",
        fake_complete_llm_response,
    )

    result = await run_agent_definition(
        agent_name="literature_synthesizer",
        source_ids=["source-1"],
        agent_input={"query": "Summarize the evidence"},
        db=None,
        llm_model="model-x",
        llm_api_base="http://localhost:4000",
        llm_api_key="key-x",
    )

    assert len(calls) == 3
    assert result["output"]["overview"] == "Recovered overview"
    assert result["output"]["key_points"] == ["Recovered point"]
    assert "raw_synthesis" not in result["output"]


@pytest.mark.asyncio
async def test_reviewer_assistant_happy_path_and_step_order(monkeypatch):
    retrieved_chunks = [
        {
            "source_id": "source-9",
            "chunk_id": "chunk-9",
            "text": "Method section context",
            "score": 0.7,
        }
    ]

    async def fake_retrieve_chunks(query, source_ids, db, mode, top_k=5, **_kwargs):
        assert "novelty concern" in query
        assert source_ids == ["source-9"]
        assert mode == "rag"
        return retrieved_chunks

    responses = iter(
        [
            '{"summary":"Address the concern","action_items":["Clarify novelty"]}',
            '{"is_valid": true, "notes": ["response matches evidence"]}',
        ]
    )

    async def fake_complete_llm_response(messages, model=None, api_base=None, api_key=None, max_tokens=None):
        assert messages[0]["role"] == "system"
        return next(responses)

    monkeypatch.setattr(reviewer_assistant, "retrieve_chunks", fake_retrieve_chunks)
    monkeypatch.setattr(
        reviewer_assistant,
        "complete_llm_response",
        fake_complete_llm_response,
    )

    result = await run_agent_definition(
        agent_name="reviewer_assistant",
        source_ids=["source-9"],
        agent_input={"review_comments": "Please address the novelty concern."},
        db=None,
        llm_model="model-x",
        llm_api_base="http://localhost:4000",
        llm_api_key="key-x",
    )

    assert [step["name"] for step in result["steps"]] == [
        "retrieve",
        "synthesize",
        "validate",
        "format_output",
    ]
    assert result["output"]["agent"] == "reviewer_assistant"
    assert result["output"]["review_comments"] == "Please address the novelty concern."
    assert result["output"]["summary"] == "Address the concern"
    assert result["output"]["validation"]["is_valid"] is True
    assert result["trace_payload"]["summary_steps"] == [
        "retrieved 1 chunks",
        "generated reviewer response draft",
        "validated reviewer response draft",
        "prepared structured response",
    ]


def test_literature_synthesizer_requests_chinese_output_for_zh_cn_locale(monkeypatch):
    captured_system_messages: list[str] = []

    async def fake_retrieve_chunks(query, source_ids, db, mode, top_k=5, **_kwargs):
        return []

    responses = iter(
        [
            '{"overview":"中文摘要","key_points":[],"contradictions":[],"gaps":[]}',
            '{"is_valid": true, "notes": []}',
        ]
    )

    async def fake_complete_llm_response(messages, model=None, api_base=None, api_key=None, max_tokens=None):
        captured_system_messages.append(messages[0]["content"])
        return next(responses)

    monkeypatch.setattr(literature_synthesizer, "retrieve_chunks", fake_retrieve_chunks)
    monkeypatch.setattr(
        literature_synthesizer,
        "complete_llm_response",
        fake_complete_llm_response,
    )

    asyncio.run(
        run_agent_definition(
            agent_name="literature_synthesizer",
            source_ids=["source-1", "source-2"],
            agent_input={"query": "Compare the findings", "locale": "zh-CN"},
            db=None,
            llm_model="model-x",
            llm_api_base="http://localhost:4000",
            llm_api_key="key-x",
        )
    )

    assert any("Respond in Simplified Chinese." in message for message in captured_system_messages)


def test_reviewer_assistant_requests_chinese_output_for_zh_cn_locale(monkeypatch):
    captured_system_messages: list[str] = []

    async def fake_retrieve_chunks(query, source_ids, db, mode, top_k=5, **_kwargs):
        return []

    responses = iter(
        [
            '{"summary":"中文总结","action_items":[],"response_outline":[]}',
            '{"is_valid": true, "notes": []}',
        ]
    )

    async def fake_complete_llm_response(messages, model=None, api_base=None, api_key=None, max_tokens=None):
        captured_system_messages.append(messages[0]["content"])
        return next(responses)

    monkeypatch.setattr(reviewer_assistant, "retrieve_chunks", fake_retrieve_chunks)
    monkeypatch.setattr(
        reviewer_assistant,
        "complete_llm_response",
        fake_complete_llm_response,
    )

    asyncio.run(
        run_agent_definition(
            agent_name="reviewer_assistant",
            source_ids=[],
            agent_input={"review_comments": "Please address novelty concerns.", "locale": "zh-CN"},
            db=None,
            llm_model="model-x",
            llm_api_base="http://localhost:4000",
            llm_api_key="key-x",
        )
    )

    assert any("Respond in Simplified Chinese." in message for message in captured_system_messages)


@pytest.mark.asyncio
async def test_agent_json_parse_fallback_does_not_crash(monkeypatch):
    async def fake_retrieve_chunks(query, source_ids, db, mode, top_k=5, **_kwargs):
        return [
            {
                "source_id": "source-1",
                "chunk_id": "chunk-1",
                "text": "Evidence snippet",
                "score": 0.6,
            }
        ]

    responses = iter(
        [
            "not valid json at all",
            "still not json",
        ]
    )

    async def fake_complete_llm_response(messages, model=None, api_base=None, api_key=None, max_tokens=None):
        return next(responses)

    monkeypatch.setattr(literature_synthesizer, "retrieve_chunks", fake_retrieve_chunks)
    monkeypatch.setattr(
        literature_synthesizer,
        "complete_llm_response",
        fake_complete_llm_response,
    )

    result = await run_agent_definition(
        agent_name="literature_synthesizer",
        source_ids=["source-1", "source-2"],
        agent_input={"query": "Compare carefully"},
        db=None,
        llm_model="model-x",
        llm_api_base="http://localhost:4000",
        llm_api_key="key-x",
    )

    assert result["output"]["overview"] == ""
    assert result["output"]["raw_synthesis"] == "not valid json at all"
    assert result["output"]["validation"]["raw_validation"] == "still not json"
    assert result["steps"][-1]["name"] == "format_output"


@pytest.mark.asyncio
async def test_literature_synthesizer_normalizes_wrong_shape_json(monkeypatch):
    async def fake_retrieve_chunks(query, source_ids, db, mode, top_k=5, **_kwargs):
        return [
            {
                "source_id": "source-1",
                "chunk_id": "chunk-1",
                "text": "Evidence snippet",
                "score": 0.6,
            }
        ]

    responses = iter(
        [
            '{"overview":["bad"],"key_points":"single point","contradictions":[1,"ok"],"gaps":null}',
            '{"is_valid":"maybe","notes":"needs work"}',
        ]
    )

    async def fake_complete_llm_response(messages, model=None, api_base=None, api_key=None, max_tokens=None):
        return next(responses)

    monkeypatch.setattr(literature_synthesizer, "retrieve_chunks", fake_retrieve_chunks)
    monkeypatch.setattr(
        literature_synthesizer,
        "complete_llm_response",
        fake_complete_llm_response,
    )

    result = await run_agent_definition(
        agent_name="literature_synthesizer",
        source_ids=["source-1", "source-2"],
        agent_input={"query": "Compare carefully"},
        db=None,
        llm_model="model-x",
        llm_api_base="http://localhost:4000",
        llm_api_key="key-x",
    )

    assert result["output"]["overview"] == ""
    assert result["output"]["key_points"] == ["single point"]
    assert result["output"]["contradictions"] == ["1", "ok"]
    assert result["output"]["gaps"] == []
    assert result["output"]["validation"]["is_valid"] is False
    assert result["output"]["validation"]["notes"] == ["needs work"]


@pytest.mark.asyncio
async def test_reviewer_assistant_parses_fenced_json_with_wrapper_text(monkeypatch):
    async def fake_retrieve_chunks(query, source_ids, db, mode, top_k=5, **_kwargs):
        return [
            {
                "source_id": "source-9",
                "chunk_id": "chunk-9",
                "text": "Method section context",
                "score": 0.7,
            }
        ]

    responses = iter(
        [
            'Here is the draft:\n```json\n{"summary":"Address concern","action_items":"Clarify novelty","response_outline":["Point A"]}\n```',
            'Validation result: {"is_valid":"true","notes":["looks grounded"]} End.',
        ]
    )

    async def fake_complete_llm_response(messages, model=None, api_base=None, api_key=None, max_tokens=None):
        return next(responses)

    monkeypatch.setattr(reviewer_assistant, "retrieve_chunks", fake_retrieve_chunks)
    monkeypatch.setattr(
        reviewer_assistant,
        "complete_llm_response",
        fake_complete_llm_response,
    )

    result = await run_agent_definition(
        agent_name="reviewer_assistant",
        source_ids=["source-9"],
        agent_input={"review_comments": "Please address the novelty concern."},
        db=None,
        llm_model="model-x",
        llm_api_base="http://localhost:4000",
        llm_api_key="key-x",
    )

    assert result["output"]["summary"] == "Address concern"
    assert result["output"]["action_items"] == ["Clarify novelty"]
    assert result["output"]["response_outline"] == ["Point A"]
    assert result["output"]["validation"]["is_valid"] is True
    assert result["output"]["validation"]["notes"] == ["looks grounded"]


def test_agent_runtime_reload_keeps_builtin_registration_stable():
    reloaded = importlib.reload(importlib.import_module("app.services.agent_runtime"))

    assert "literature_synthesizer" in reloaded.AGENT_REGISTRY
    assert "reviewer_assistant" in reloaded.AGENT_REGISTRY


@pytest.mark.asyncio
async def test_run_agent_definition_rejects_unknown_agent(monkeypatch):
    runtime_module = importlib.import_module("app.services.agent_runtime")
    monkeypatch.setattr(runtime_module, "AGENT_REGISTRY", {})

    with pytest.raises(runtime_module.UnknownAgentError):
        await runtime_module.run_agent_definition(
            agent_name="missing-agent",
            source_ids=[],
            agent_input={},
            db=None,
            llm_model=None,
            llm_api_base=None,
            llm_api_key=None,
        )


def test_register_agent_definition_rejects_duplicates(monkeypatch):
    runtime_module = importlib.import_module("app.services.agent_runtime")
    monkeypatch.setattr(runtime_module, "AGENT_REGISTRY", {})

    async def fake_runner(**kwargs):
        return {
            "output": {},
            "steps": [],
            "trace_payload": {},
        }

    definition = AgentDefinition(name="duplicate-agent", runner=fake_runner)
    runtime_module.register_agent_definition(definition)

    with pytest.raises(runtime_module.DuplicateAgentRegistrationError):
        runtime_module.register_agent_definition(definition)


@pytest.mark.asyncio
async def test_complete_llm_response_joins_stream_tokens(monkeypatch):
    async def fake_stream(*args, **kwargs):
        yield "hello"
        yield " "
        yield "world"

    monkeypatch.setattr(llm_service, "stream_llm_response", fake_stream)

    result = await llm_service.complete_llm_response(
        [{"role": "user", "content": "hello"}],
        model="model-x",
        api_base="http://localhost:4000",
        api_key="key-x",
    )

    assert result == "hello world"


@pytest.mark.asyncio
async def test_stream_llm_response_ignores_empty_provider_events(monkeypatch):
    class FakeResponse:
        def __aiter__(self):
            async def generator():
                yield SimpleNamespace(choices=[])
                yield SimpleNamespace(choices=[SimpleNamespace()])
                yield SimpleNamespace(choices=[SimpleNamespace(delta=None)])
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace())])
                yield SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content=None))]
                )
                yield SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content="ok"))]
                )

            return generator()

    async def fake_acompletion(**kwargs):
        return FakeResponse()

    monkeypatch.setattr(llm_service.litellm, "acompletion", fake_acompletion)

    chunks = []
    async for token in llm_service.stream_llm_response(
        [{"role": "user", "content": "hello"}],
        model="model-x",
        api_base="http://localhost:4000",
        api_key="key-x",
    ):
        chunks.append(token)

    assert chunks == ["ok"]
