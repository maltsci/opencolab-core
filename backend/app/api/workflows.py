from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agents import (
    _build_relation_response,
    _build_research_object_response,
    _validate_session_sources,
)
from app.api.sessions import _get_session_for_user
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.message import Message
from app.models.research_object import ResearchObject, ResearchObjectRelation
from app.models.session import Session
from app.models.source import SessionSource
from app.models.trace import ResearchTrace
from app.models.user import User
from app.models.workflow_run import StepRun, WorkflowRun
from app.schemas.workflow import (
    StepRunResponse,
    WorkflowDefinition,
    WorkflowRunCreateRequest,
    WorkflowRunResponse,
    WorkflowRunSaveMemoryRequest,
    WorkflowRunSaveMemoryResponse,
)
from app.services.agent_runtime import run_agent_definition
from app.services.research_context import collect_project_source_ids
from app.services.research_asset_service import materialize_research_object_asset
from app.services.runtime_config import get_runtime_llm_api_key, get_runtime_value
from app.services.source_group_service import expand_source_ids_for_rag
from app.workflows.executor import WorkflowExecutionError, run_workflow_definition
from app.workflows.registry import (
    UnknownWorkflowError,
    get_workflow_definition,
    list_workflow_definitions,
)

router = APIRouter(tags=["workflows"])


def _format_workflow_output_value(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        items = [
            _format_workflow_output_value(item)
            for item in value
            if _format_workflow_output_value(item)
        ]
        return "\n".join(f"- {item}" for item in items)
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            formatted = _format_workflow_output_value(item)
            if formatted:
                parts.append(f"{key}: {formatted}")
        return "\n".join(parts)
    if value is None:
        return ""
    return str(value)


def _build_workflow_message_content(output: dict) -> str:
    preferred_keys = [
        "overview",
        "summary",
        "draft",
        "key_points",
        "contradictions",
        "gaps",
        "raw_synthesis",
    ]
    sections: list[str] = []

    for key in preferred_keys:
        value = output.get(key)
        formatted = _format_workflow_output_value(value)
        if not formatted:
            continue
        if key in {"overview", "summary", "draft", "raw_synthesis"}:
            sections.append(formatted)
        else:
            sections.append(f"{key}\n{formatted}")

    if sections:
        return "\n\n".join(sections)

    fallback_sections = []
    for key, value in output.items():
        if key in {"agent", "citations", "validation"}:
            continue
        formatted = _format_workflow_output_value(value)
        if formatted:
            fallback_sections.append(f"{key}\n{formatted}")
    return "\n\n".join(fallback_sections)


async def _collect_session_source_ids(
    *,
    session: Session,
    db: AsyncSession,
) -> list[str]:
    result = await db.execute(
        select(SessionSource.source_id).where(SessionSource.session_id == session.id)
    )
    return list(result.scalars().all())


@router.get("/workflows", response_model=list[WorkflowDefinition])
async def list_workflows(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_workflow_definitions(db)


@router.get("/workflows/{workflow_id}", response_model=WorkflowDefinition)
async def get_workflow(
    workflow_id: str,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await get_workflow_definition(workflow_id, db)
    except UnknownWorkflowError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc


@router.post(
    "/workflows/{workflow_id}/run",
    response_model=WorkflowRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def run_workflow(
    workflow_id: str,
    body: WorkflowRunCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_session_for_user(body.session_id, user, db)
    try:
        workflow = await get_workflow_definition(workflow_id, db)
    except UnknownWorkflowError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc

    is_builtin_workflow = workflow.id in {"literature_synthesizer", "reviewer_assistant"}

    llm_model = await get_runtime_value("llm_model", db)
    llm_api_base = await get_runtime_value("llm_api_base", db)
    llm_api_key = await get_runtime_llm_api_key(db)

    raw_source_ids = body.input.get("source_ids", [])
    if not isinstance(raw_source_ids, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_ids must be a list when provided",
        )
    if "source_ids" not in body.input:
        raw_source_ids = await collect_project_source_ids(
            db=db,
            project_id=session.project_id,
            user=user,
        )
        if not raw_source_ids:
            raw_source_ids = await _collect_session_source_ids(session=session, db=db)
    expanded_source_ids = await expand_source_ids_for_rag(raw_source_ids, db)
    await _validate_session_sources(
        session_id=session.id,
        source_ids=expanded_source_ids,
        user=user,
        db=db,
        project_id=session.project_id,
        agent_run_id=f"workflow:{workflow_id}:{session.id}",
    )

    try:
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
            legacy_agent_runner=run_agent_definition if is_builtin_workflow else None,
        )
    except WorkflowExecutionError as exc:
        # This route currently passes the read-only legacy runner. Future mutating
        # skill runners must isolate audit persistence before sharing a transaction.
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Workflow execution failed.",
        ) from exc

    trace_payload = execution.trace_payload
    assistant_message_content = _build_workflow_message_content(execution.output)
    assistant_message: Message | None = None
    if assistant_message_content:
        if body.replace_message_id:
            assistant_message = await db.scalar(
                select(Message).where(
                    Message.id == body.replace_message_id,
                    Message.session_id == session.id,
                    Message.role == "assistant",
                )
            )
            if assistant_message is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Message to replace not found",
                )
            assistant_message.content = assistant_message_content
        else:
            assistant_message = Message(
                session_id=session.id,
                role="assistant",
                content=assistant_message_content,
            )
            db.add(assistant_message)
        await db.flush()

    existing_trace: ResearchTrace | None = None
    if body.replace_message_id:
        existing_trace = await db.scalar(
            select(ResearchTrace).where(
                ResearchTrace.session_id == session.id,
                ResearchTrace.message_id == body.replace_message_id,
            )
        )

    if existing_trace is not None:
        existing_trace.workflow_run_id = execution.workflow_run.id
        existing_trace.inputs_json = trace_payload.get("inputs", {})
        existing_trace.retrieval_json = trace_payload.get("retrieval", [])
        existing_trace.citations_json = trace_payload.get("citations", [])
        existing_trace.summary_steps_json = trace_payload.get("summary_steps", [])
    else:
        trace = ResearchTrace(
            session_id=session.id,
            message_id=assistant_message.id if assistant_message is not None else None,
            user_id=user.id,
            workflow_run_id=execution.workflow_run.id,
            inputs_json=trace_payload.get("inputs", {}),
            retrieval_json=trace_payload.get("retrieval", []),
            citations_json=trace_payload.get("citations", []),
            summary_steps_json=trace_payload.get("summary_steps", []),
        )
        db.add(trace)
    await db.commit()
    await db.refresh(execution.workflow_run)
    return WorkflowRunResponse.model_validate(execution.workflow_run)


async def _get_workflow_run_for_user(
    run_id: str,
    user: User,
    db: AsyncSession,
) -> WorkflowRun:
    workflow_run = await db.scalar(
        select(WorkflowRun).where(
            WorkflowRun.id == run_id,
            WorkflowRun.created_by == user.id,
        )
    )
    if workflow_run is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    await _get_session_for_user(workflow_run.session_id, user, db)
    return workflow_run


@router.get(
    "/sessions/{session_id}/workflow-runs",
    response_model=list[WorkflowRunResponse],
)
async def list_session_workflow_runs(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_session_for_user(session_id, user, db)
    result = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.session_id == session.id)
        .order_by(WorkflowRun.created_at.desc(), WorkflowRun.id.desc())
    )
    return [
        WorkflowRunResponse.model_validate(workflow_run)
        for workflow_run in result.scalars().all()
    ]


@router.get("/workflow-runs/{run_id}", response_model=WorkflowRunResponse)
async def get_workflow_run(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workflow_run = await _get_workflow_run_for_user(run_id, user, db)
    return WorkflowRunResponse.model_validate(workflow_run)


@router.post(
    "/workflow-runs/{run_id}/save-memory",
    response_model=WorkflowRunSaveMemoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_workflow_run_to_memory(
    run_id: str,
    body: WorkflowRunSaveMemoryRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workflow_run = await _get_workflow_run_for_user(run_id, user, db)
    session = await _get_session_for_user(workflow_run.session_id, user, db)
    if workflow_run.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only completed workflow runs can be saved to memory",
        )

    trace = await db.scalar(
        select(ResearchTrace)
        .where(ResearchTrace.workflow_run_id == workflow_run.id)
        .order_by(ResearchTrace.created_at.desc(), ResearchTrace.id.desc())
    )
    trace_inputs = trace.inputs_json if trace is not None else {}
    source_ids = trace_inputs.get("source_ids") if isinstance(trace_inputs, dict) else []
    citations = trace.citations_json if trace is not None else []

    research_object = ResearchObject(
        type=body.type,
        title=body.title,
        content=body.content,
        content_json={
            "project_id": session.project_id,
            "session_id": workflow_run.session_id,
            "source_session_id": workflow_run.session_id,
            "origin": "workflow_run",
            "workflow_run_id": workflow_run.id,
            "trace_id": trace.id if trace is not None else None,
            "source_ids": source_ids if isinstance(source_ids, list) else [],
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
        target_object = await db.scalar(
            select(ResearchObject).where(
                ResearchObject.id == body.relation.target_object_id,
            )
        )
        if target_object is None:
            await db.rollback()
            raise HTTPException(status_code=404, detail="Target research object not found")
        if target_object.content_json.get("session_id") != workflow_run.session_id:
            await db.rollback()
            raise HTTPException(
                status_code=400,
                detail="Target research object must belong to the same session",
            )

        evidence = {
            "trace_id": trace.id if trace is not None else None,
            "citations": citations if isinstance(citations, list) else [],
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

    return WorkflowRunSaveMemoryResponse(
        research_object=_build_research_object_response(research_object),
        relation=response_relation,
    )


@router.get("/workflow-runs/{run_id}/steps", response_model=list[StepRunResponse])
async def list_workflow_run_steps(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workflow_run = await _get_workflow_run_for_user(run_id, user, db)
    result = await db.execute(
        select(StepRun)
        .where(StepRun.workflow_run_id == workflow_run.id)
        .order_by(StepRun.created_at)
    )
    return [StepRunResponse.model_validate(step) for step in result.scalars().all()]


@router.post("/workflow-runs/{run_id}/cancel", response_model=WorkflowRunResponse)
async def cancel_workflow_run(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workflow_run = await _get_workflow_run_for_user(run_id, user, db)
    if workflow_run.status in {"pending", "running", "waiting_for_checkpoint"}:
        workflow_run.status = "cancelled"
        workflow_run.finished_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(workflow_run)
    return WorkflowRunResponse.model_validate(workflow_run)
