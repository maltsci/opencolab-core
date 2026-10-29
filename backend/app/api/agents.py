import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.sessions import _get_session_for_user
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.agent_run import AgentRun
from app.models.message import Message
from app.models.research_object import ResearchObject, ResearchObjectRelation
from app.models.trace import ResearchTrace
from app.models.user import User
from app.schemas.agent import (
    AgentRunCreateRequest,
    AgentRunResponse,
    AgentRunSaveMemoryRequest,
    AgentRunSaveMemoryResponse,
)
from app.schemas.research_object import ResearchObjectResponse
from app.schemas.research_object_relation import (
    ResearchObjectRelationResponse,
    ResearchObjectRelationTarget,
    normalize_relation_metadata,
)
from app.services.agent_runtime import UnknownAgentError, run_agent_definition
from app.services.research_asset_service import materialize_research_object_asset
from app.services.runtime_config import get_runtime_llm_api_key, get_runtime_value
from app.services.sharing_service import can_user_use_source_in_agent
from app.services.source_group_service import expand_source_ids_for_rag
from app.workflows.executor import WorkflowExecutionError, run_workflow_definition
from app.workflows.registry import UnknownWorkflowError, get_workflow_definition

router = APIRouter(prefix="/agents", tags=["agents"])


async def _validate_session_sources(
    *,
    session_id: str,
    source_ids: list[str],
    user: User,
    db: AsyncSession,
    project_id: str | None = None,
    agent_run_id: str | None = None,
) -> None:
    if not source_ids:
        return

    inaccessible_source_ids = [
        source_id
        for source_id in source_ids
        if not await can_user_use_source_in_agent(
            user=user,
            source_id=source_id,
            project_id=project_id,
            purpose="Use selected source in Agent workflow",
            agent_run_id=agent_run_id or f"session:{session_id}",
            db=db,
        )
    ]
    if inaccessible_source_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="All selected sources must be linked to the session.",
        )


async def _get_agent_run_for_user(
    run_id: str,
    user: User,
    db: AsyncSession,
) -> AgentRun:
    result = await db.execute(
        select(AgentRun)
        .options(selectinload(AgentRun.traces))
        .where(
            AgentRun.id == run_id,
            AgentRun.user_id == user.id,
        )
    )
    agent_run = result.scalar_one_or_none()
    if agent_run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return agent_run


def _build_research_object_response(research_object: ResearchObject) -> ResearchObjectResponse:
    payload = ResearchObjectResponse.model_validate(research_object).model_dump()
    payload["session_id"] = research_object.content_json.get("session_id")
    payload["message_id"] = research_object.content_json.get("source_message_id")
    return ResearchObjectResponse(**payload)


def _build_relation_response(
    relation: ResearchObjectRelation,
    target_object: ResearchObject,
) -> ResearchObjectRelationResponse:
    return ResearchObjectRelationResponse(
        id=relation.id,
        relation_type=relation.relation_type,
        source_object_id=relation.source_object_id,
        target_object_id=relation.target_object_id,
        metadata_json=normalize_relation_metadata(relation.metadata_json),
        created_by=relation.created_by,
        created_by_type=relation.created_by_type,
        target_object=ResearchObjectRelationTarget(
            id=target_object.id,
            type=target_object.type,
            title=target_object.title,
        ),
        created_at=relation.created_at,
    )


def _parse_raw_json_object(value: object) -> dict | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _format_agent_message_from_payload(agent_name: str, payload: dict) -> str:
    if agent_name == "literature_synthesizer":
        sections: list[str] = []
        overview = payload.get("overview")
        if isinstance(overview, str) and overview.strip():
            sections.append(overview.strip())

        for key in ("key_points", "contradictions", "gaps"):
            value = payload.get(key)
            if isinstance(value, list):
                items = [str(item).strip() for item in value if str(item).strip()]
                if items:
                    sections.append(f"{key}\n" + "\n".join(f"- {item}" for item in items))

        if sections:
            return "\n\n".join(sections)

    if agent_name == "reviewer_assistant":
        summary = payload.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()

    return ""


def _build_agent_message_content(agent_name: str, output: dict) -> str:
    formatted = _format_agent_message_from_payload(agent_name, output)
    if formatted:
        return formatted

    raw_synthesis = output.get("raw_synthesis")
    parsed_raw = _parse_raw_json_object(raw_synthesis)
    if parsed_raw is not None:
        formatted = _format_agent_message_from_payload(agent_name, parsed_raw)
        if formatted:
            return formatted

    return ""


def _build_agent_step_records(workflow_steps) -> list[dict]:
    records: list[dict] = []
    for step in workflow_steps:
        output_payload = step.output_payload or {}
        records.append(
            {
                "name": output_payload.get("name") or step.step_id,
                "status": output_payload.get("status") or step.status,
                "summary": output_payload.get("summary") or "",
            }
        )
    return records


@router.post("/run", response_model=AgentRunResponse, status_code=status.HTTP_201_CREATED)
async def run_agent(
    body: AgentRunCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_session_for_user(body.session_id, user, db)
    expanded_source_ids = await expand_source_ids_for_rag(
        body.source_ids,
        db,
    )
    await _validate_session_sources(
        session_id=session.id,
        source_ids=expanded_source_ids,
        user=user,
        db=db,
        project_id=session.project_id,
        agent_run_id=f"agent:{session.id}",
    )

    llm_model = await get_runtime_value("llm_model", db)
    llm_api_base = await get_runtime_value("llm_api_base", db)
    llm_api_key = await get_runtime_llm_api_key(db)

    agent_run = AgentRun(
        session_id=session.id,
        user_id=user.id,
        agent_name=body.agent,
        status="running",
        input_json=body.input,
    )
    db.add(agent_run)
    await db.commit()
    await db.refresh(agent_run)

    try:
        workflow = get_workflow_definition(body.agent)
        execution = await run_workflow_definition(
            workflow=workflow,
            session_id=session.id,
            user_id=user.id,
            source_ids=expanded_source_ids,
            input_payload=body.input,
            db=db,
            llm_model=llm_model,
            llm_api_base=llm_api_base,
            llm_api_key=llm_api_key,
            legacy_agent_runner=run_agent_definition,
        )
    except (UnknownAgentError, UnknownWorkflowError) as exc:
        agent_run.status = "failed"
        agent_run.error_message = "Unknown agent"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unknown agent.",
        ) from exc
    except WorkflowExecutionError as exc:
        agent_run.status = "failed"
        agent_run.workflow_run_id = exc.workflow_run_id
        if isinstance(exc.original_error, UnknownAgentError):
            agent_run.error_message = "Unknown agent"
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unknown agent.",
            ) from exc
        agent_run.error_message = "Agent execution failed."
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Agent execution failed.",
        ) from exc

    trace_payload = execution.trace_payload
    agent_run.status = "completed"
    agent_run.workflow_run_id = execution.workflow_run.id
    agent_run.steps_json = execution.legacy_steps or _build_agent_step_records(
        execution.steps
    )
    agent_run.output_json = execution.output
    agent_run.error_message = None

    assistant_message = Message(
        session_id=session.id,
        role="assistant",
        content=_build_agent_message_content(
            agent_run.agent_name,
            execution.output,
        ),
    )
    db.add(assistant_message)
    await db.flush()

    trace = ResearchTrace(
        session_id=session.id,
        message_id=assistant_message.id,
        user_id=user.id,
        agent_run_id=agent_run.id,
        workflow_run_id=execution.workflow_run.id,
        inputs_json=trace_payload.get("inputs", {}),
        retrieval_json=trace_payload.get("retrieval", []),
        citations_json=trace_payload.get("citations", []),
        summary_steps_json=trace_payload.get("summary_steps", []),
    )
    db.add(trace)
    await db.commit()

    result = await db.execute(
        select(AgentRun)
        .options(selectinload(AgentRun.traces))
        .where(AgentRun.id == agent_run.id)
    )
    persisted_run = result.scalar_one()
    return AgentRunResponse.model_validate(persisted_run)


@router.get("/runs/{run_id}", response_model=AgentRunResponse)
async def get_agent_run(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent_run = await _get_agent_run_for_user(run_id, user, db)
    return AgentRunResponse.model_validate(agent_run)


@router.post(
    "/runs/{run_id}/save-memory",
    response_model=AgentRunSaveMemoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_agent_run_to_memory(
    run_id: str,
    body: AgentRunSaveMemoryRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent_run = await _get_agent_run_for_user(run_id, user, db)
    session = await _get_session_for_user(agent_run.session_id, user, db)

    trace_payload = AgentRunResponse.model_validate(agent_run).trace
    trace_inputs = trace_payload.inputs if trace_payload else {}
    trace_id = None
    citations: list[dict] = []
    if agent_run.traces:
        selected_trace = max(
            agent_run.traces,
            key=AgentRunResponse._trace_sort_key,
        )
        trace_id = selected_trace.id
        citations = selected_trace.citations_json or []

    research_object = ResearchObject(
        type=body.type,
        title=body.title,
        content=body.content,
        content_json={
            "project_id": session.project_id,
            "session_id": agent_run.session_id,
            "source_session_id": agent_run.session_id,
            "origin": "agent_run",
            "agent_run_id": agent_run.id,
            "trace_id": trace_id,
            "source_ids": trace_inputs.get("source_ids", [])
            if isinstance(trace_inputs.get("source_ids"), list)
            else [],
        },
        created_by=user.id,
    )
    db.add(research_object)
    await db.flush()
    await materialize_research_object_asset(
        db=db,
        research_object=research_object,
        owner_id=user.id,
        origin_project_id=session.project_id,
        origin_session_id=session.id,
        visibility_scope="project" if session.project_id else "private",
        link_type="memory",
    )

    relation: ResearchObjectRelation | None = None
    target_object: ResearchObject | None = None
    if body.relation.enabled:
        target_result = await db.execute(
            select(ResearchObject).where(
                ResearchObject.id == body.relation.target_object_id,
            )
        )
        target_object = target_result.scalar_one_or_none()
        if target_object is None:
            await db.rollback()
            raise HTTPException(status_code=404, detail="Target research object not found")
        if target_object.content_json.get("session_id") != agent_run.session_id:
            await db.rollback()
            raise HTTPException(
                status_code=400,
                detail="Target research object must belong to the same session",
            )

        evidence = {
            "trace_id": trace_id,
            "citations": citations,
        }
        if body.relation.note and body.relation.note.strip():
            evidence["note"] = body.relation.note.strip()

        relation = ResearchObjectRelation(
            source_object_id=research_object.id,
            target_object_id=target_object.id,
            relation_type=body.relation.relation_type,
            metadata_json={
                "confidence": 0.8,
                "evidence": evidence,
            },
            created_by=user.id,
            created_by_type="human",
        )
        db.add(relation)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Research relation already exists",
        ) from exc

    await db.refresh(research_object)
    response_relation = None
    if relation is not None and target_object is not None:
        await db.refresh(relation)
        response_relation = _build_relation_response(relation, target_object)

    return AgentRunSaveMemoryResponse(
        research_object=_build_research_object_response(research_object),
        relation=response_relation,
    )
