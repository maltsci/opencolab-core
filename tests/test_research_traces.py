from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.models.session import Session
from app.models.trace import ResearchTrace
from app.models.user import Workspace
from app.api.websocket import _get_session_for_websocket_user
from app.schemas.trace import ResearchTraceResponse
from app.services.citation_service import build_citations
from app.services.trace_service import build_trace_payload

def test_build_citations_returns_v0_snippets():
    citations = build_citations(
        [
            {
                "source_id": "src-1",
                "chunk_id": "chunk-1",
                "text": "Evidence " * 50,
                "score": 0.91,
            }
        ]
    )

    assert citations == [
        {
            "source_id": "src-1",
            "chunk_id": "chunk-1",
            "snippet": ("Evidence " * 50)[:280],
            "score": 0.91,
        }
    ]


def test_trace_payload_only_contains_v0_fields():
    payload = build_trace_payload(
        query="What does this paper claim?",
        source_ids=["src-1"],
        retrieved_chunks=[
            {
                "source_id": "src-1",
                "chunk_id": "c1",
                "score": 0.9,
                "text": "chunk",
            }
        ],
    )

    assert set(payload.keys()) == {
        "inputs",
        "retrieval",
        "citations",
        "summary_steps",
    }
    assert payload["inputs"]["query"] == "What does this paper claim?"
    assert payload["retrieval"][0]["chunk_id"] == "c1"
    assert payload["retrieval"][0]["snippet"] == "chunk"
    assert payload["citations"][0]["snippet"] == "chunk"
    assert payload["summary_steps"] == [
        "selected 1 documents",
        "retrieved 1 relevant chunks",
        "generated answer with 1 citations",
    ]


def test_trace_payload_uses_chinese_summary_steps_for_zh_cn():
    payload = build_trace_payload(
        query="这篇论文讲了什么？",
        source_ids=["src-1"],
        retrieved_chunks=[
            {
                "source_id": "src-1",
                "chunk_id": "c1",
                "score": 0.9,
                "text": "chunk",
            }
        ],
        locale="zh-CN",
    )

    assert payload["summary_steps"] == [
        "已选择 1 份文档",
        "已检索到 1 个相关片段",
        "已生成答案并附带 1 条引用",
    ]


def test_research_trace_response_maps_json_fields():
    payload = {
        "id": "trace-1",
        "session_id": "session-1",
        "message_id": "message-1",
        "workflow_run_id": "workflow-run-1",
        "inputs_json": {"question": "What changed?"},
        "retrieval_json": [{"source_id": "src-1"}],
        "citations_json": [{"source_id": "src-1", "quote": "A"}],
        "summary_steps_json": ["collect", "compare"],
        "created_at": datetime(2026, 6, 26, tzinfo=UTC),
    }

    result = ResearchTraceResponse.model_validate(payload)

    assert result.inputs == {"question": "What changed?"}
    assert result.workflow_run_id == "workflow-run-1"
    assert result.retrieval == [{"source_id": "src-1"}]
    assert result.citations[0]["quote"] == "A"
    assert result.summary_steps == ["collect", "compare"]


@pytest.mark.asyncio
async def test_list_session_traces_returns_latest_first(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
):
    workspace_id = await db.scalar(
        select(Workspace.id).where(Workspace.researcher_id == researcher_user.id)
    )
    session = Session(workspace_id=workspace_id, title="Trace Session")
    db.add(session)
    await db.flush()

    first_message = Message(
        session_id=session.id,
        role="assistant",
        content="First answer",
    )
    second_message = Message(
        session_id=session.id,
        role="assistant",
        content="Second answer",
    )
    db.add_all([first_message, second_message])
    await db.flush()

    first_trace = ResearchTrace(
        session_id=session.id,
        message_id=first_message.id,
        user_id=researcher_user.id,
        inputs_json={"query": "first"},
        retrieval_json=[{"chunk_id": "chunk-1"}],
        citations_json=[{"chunk_id": "chunk-1", "snippet": "first"}],
        summary_steps_json=["first step"],
        created_at=datetime(2026, 6, 26, 0, 0, 1, tzinfo=UTC),
    )
    second_trace = ResearchTrace(
        session_id=session.id,
        message_id=second_message.id,
        user_id=researcher_user.id,
        inputs_json={"query": "second"},
        retrieval_json=[{"chunk_id": "chunk-2"}],
        citations_json=[{"chunk_id": "chunk-2", "snippet": "second"}],
        summary_steps_json=["second step"],
        created_at=datetime(2026, 6, 26, 0, 0, 2, tzinfo=UTC),
    )
    db.add_all([first_trace, second_trace])
    await db.commit()

    response = await client.get(
        f"/api/v1/sessions/{session.id}/trace",
        headers=researcher_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == [second_trace.id, first_trace.id]
    assert payload[0]["citations"][0]["snippet"] == "second"
    assert payload[1]["summary_steps"] == ["first step"]


@pytest.mark.asyncio
async def test_list_session_traces_prefers_message_timestamp_when_trace_timestamps_tie(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
):
    workspace_id = await db.scalar(
        select(Workspace.id).where(Workspace.researcher_id == researcher_user.id)
    )
    session = Session(workspace_id=workspace_id, title="Trace Session")
    db.add(session)
    await db.flush()

    earlier_message = Message(
        session_id=session.id,
        role="assistant",
        content="Earlier answer",
        created_at=datetime(2026, 6, 26, 0, 0, 1, tzinfo=UTC),
    )
    later_message = Message(
        session_id=session.id,
        role="assistant",
        content="Later answer",
        created_at=datetime(2026, 6, 26, 0, 0, 2, tzinfo=UTC),
    )
    db.add_all([earlier_message, later_message])
    await db.flush()

    tied_created_at = datetime(2026, 6, 26, 0, 0, 3, tzinfo=UTC)
    older_trace = ResearchTrace(
        session_id=session.id,
        message_id=earlier_message.id,
        user_id=researcher_user.id,
        inputs_json={"query": "first"},
        retrieval_json=[],
        citations_json=[{"snippet": "earlier"}],
        summary_steps_json=["earlier step"],
        created_at=tied_created_at,
    )
    newer_trace = ResearchTrace(
        session_id=session.id,
        message_id=later_message.id,
        user_id=researcher_user.id,
        inputs_json={"query": "second"},
        retrieval_json=[],
        citations_json=[{"snippet": "later"}],
        summary_steps_json=["later step"],
        created_at=tied_created_at,
    )
    db.add_all([older_trace, newer_trace])
    await db.commit()

    response = await client.get(
        f"/api/v1/sessions/{session.id}/trace",
        headers=researcher_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == [newer_trace.id, older_trace.id]


@pytest.mark.asyncio
async def test_list_session_traces_respects_workspace_isolation(
    client: AsyncClient,
    auth_headers: dict,
    researcher_headers: dict,
):
    create = await client.post(
        "/api/v1/sessions",
        json={"title": "Admin Session"},
        headers=auth_headers,
    )
    session_id = create.json()["id"]

    response = await client.get(
        f"/api/v1/sessions/{session_id}/trace",
        headers=researcher_headers,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_websocket_session_auth_helper_rejects_other_workspace_session(
    admin_user,
    researcher_user,
    db: AsyncSession,
):
    admin_workspace_id = await db.scalar(
        select(Workspace.id).where(Workspace.researcher_id == admin_user.id)
    )
    session = Session(workspace_id=admin_workspace_id, title="Admin Session")
    db.add(session)
    await db.commit()

    authorized_session = await _get_session_for_websocket_user(
        session.id,
        researcher_user.id,
        db,
    )

    assert authorized_session is None
