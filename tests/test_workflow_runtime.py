import pytest
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.models.session import Session
from app.models.user import User, Workspace
from app.models.workflow_run import StepRun, WorkflowRun
from app.schemas.workflow import WorkflowDefinition, WorkflowStepDefinition
from app.workflows.executor import WorkflowExecutionError, run_workflow_definition
from app.workflows.registry import (
    UnknownWorkflowError,
    _build_registry as build_workflow_registry,
    get_workflow_definition,
    list_workflow_definitions,
)


async def _create_workflow_test_session(db: AsyncSession) -> tuple[str, str]:
    user = User(
        id="user-1",
        username="workflow-user",
        hashed_password="test-password",
    )
    db.add(user)
    await db.flush()

    workspace = Workspace(researcher_id=user.id)
    db.add(workspace)
    await db.flush()

    session = Session(
        id="session-1",
        workspace_id=workspace.id,
        title="Workflow test session",
    )
    db.add(session)
    await db.flush()
    return session.id, user.id


async def test_workflow_tables_are_registered(db: AsyncSession):
    result = await db.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    table_names = {name for (name,) in result.all()}

    assert "workflow_runs" in Base.metadata.tables
    assert "step_runs" in Base.metadata.tables
    assert "workflow_runs" in table_names
    assert "step_runs" in table_names

    agent_runs_table = Base.metadata.tables["agent_runs"]
    research_traces_table = Base.metadata.tables["research_traces"]
    assert "workflow_run_id" in agent_runs_table.c
    assert "workflow_run_id" in research_traces_table.c


def test_builtin_workflow_registry_contains_current_agents():
    workflow_ids = {workflow.id for workflow in list_workflow_definitions()}
    literature_workflow = get_workflow_definition("literature_synthesizer")
    reviewer_workflow = get_workflow_definition("reviewer_assistant")

    assert workflow_ids == {"literature_synthesizer", "reviewer_assistant"}
    assert [step.id for step in literature_workflow.steps] == [
        "retrieve",
        "synthesize",
        "validate",
        "format_output",
    ]
    assert [step.id for step in reviewer_workflow.steps] == [
        "retrieve",
        "draft_response",
        "validate",
        "format_output",
    ]

    reviewer_draft_step = reviewer_workflow.steps[1]
    assert reviewer_draft_step.ref == "reviewer-response-draft"
    assert reviewer_draft_step.depends_on == ["retrieve"]
    assert reviewer_draft_step.output_key == "draft"
    assert reviewer_workflow.steps[2].depends_on == ["draft_response"]


def test_registry_unknown_workflow_id_raises_lookup_error():
    with pytest.raises(UnknownWorkflowError):
        get_workflow_definition("unknown_workflow")


def test_registry_builder_rejects_duplicate_ids():
    duplicate_workflow = WorkflowDefinition(
        id="duplicate_workflow",
        name="Duplicate Workflow",
        description="Duplicate workflow definition.",
        steps=[
            WorkflowStepDefinition(
                id="retrieve",
                type="skill",
                ref="rag-retrieve",
                output_key="retrieved_chunks",
            )
        ],
    )
    with pytest.raises(ValueError):
        build_workflow_registry([duplicate_workflow, duplicate_workflow])


def test_workflow_registry_returns_mutation_safe_copies():
    retrieved_workflow = get_workflow_definition("reviewer_assistant")
    retrieved_workflow.steps[1].id = "mutated"
    retrieved_workflow.steps[1].depends_on.append("mutated-dependency")

    listed_workflow = next(
        workflow
        for workflow in list_workflow_definitions()
        if workflow.id == "reviewer_assistant"
    )
    listed_workflow.steps[1].id = "listed_mutated"
    listed_workflow.steps[1].depends_on.append("listed-mutated-dependency")

    fresh_workflow = get_workflow_definition("reviewer_assistant")
    assert [step.id for step in fresh_workflow.steps] == [
        "retrieve",
        "draft_response",
        "validate",
        "format_output",
    ]
    assert fresh_workflow.steps[1].depends_on == ["retrieve"]


async def test_run_workflow_definition_persists_step_runs(db: AsyncSession):
    session_id, user_id = await _create_workflow_test_session(db)
    workflow = get_workflow_definition("reviewer_assistant")

    result = await run_workflow_definition(
        workflow=workflow,
        session_id=session_id,
        user_id=user_id,
        source_ids=[],
        input_payload={"review_comments": "Please address novelty concerns."},
        db=db,
        llm_model=None,
        llm_api_base=None,
        llm_api_key=None,
        legacy_agent_runner=None,
    )

    persisted = await db.scalar(
        select(WorkflowRun).where(WorkflowRun.id == result.workflow_run.id)
    )
    steps = (
        await db.execute(
            select(StepRun)
            .where(StepRun.workflow_run_id == result.workflow_run.id)
            .order_by(StepRun.created_at)
        )
    ).scalars().all()
    step_payloads = {step.step_id: step.output_payload for step in steps}

    assert persisted is not None
    assert persisted.status == "completed"
    assert [step.step_id for step in steps] == [
        "retrieve",
        "draft_response",
        "validate",
        "format_output",
    ]
    # Without a legacy agent runner, steps complete with placeholder payloads.
    assert step_payloads["retrieve"] == {
        "name": "retrieve",
        "status": "completed",
        "summary": "Executed step ref: rag-retrieve",
    }
    assert result.output["agent"] == "reviewer_assistant"
    assert result.output["input"] == {
        "review_comments": "Please address novelty concerns."
    }
    assert result.trace_payload == {
        "inputs": {"review_comments": "Please address novelty concerns."},
        "retrieval": [],
        "citations": [],
        "summary_steps": [],
    }
    assert result.legacy_steps == []


async def test_run_workflow_definition_uses_legacy_runner_outputs(
    db: AsyncSession,
):
    session_id, user_id = await _create_workflow_test_session(db)
    workflow = get_workflow_definition("reviewer_assistant")
    input_payload = {"review_comments": "Please address novelty concerns."}
    output_payload = {"agent": "reviewer_assistant", "summary": "Address concerns"}
    trace_payload = {
        "inputs": input_payload,
        "retrieval": [{"source_id": "source-1"}],
        "citations": [{"source_id": "source-1", "quote": "Novelty concern"}],
        "summary_steps": ["Retrieved sources", "Formatted response"],
    }
    calls = []

    async def fake_runner(**kwargs):
        calls.append(kwargs)
        return {
            "output": output_payload,
            "steps": [
                {
                    "name": "retrieve",
                    "status": "completed",
                    "summary": "Retrieved reviewer context",
                },
                {
                    "name": "format_output",
                    "status": "completed",
                    "summary": "Formatted response",
                },
            ],
            "trace_payload": trace_payload,
        }

    result = await run_workflow_definition(
        workflow=workflow,
        session_id=session_id,
        user_id=user_id,
        source_ids=["source-1"],
        input_payload=input_payload,
        db=db,
        llm_model="model-1",
        llm_api_base="https://llm.example.test",
        llm_api_key="test-key",
        legacy_agent_runner=fake_runner,
    )

    assert len(calls) == 1
    call = calls[0]
    assert call.pop("access_agent_run_id").startswith("workflow:")
    assert call == {
        "agent_name": "reviewer_assistant",
        "source_ids": ["source-1"],
        "agent_input": input_payload,
        "db": db,
        "llm_model": "model-1",
        "llm_api_base": "https://llm.example.test",
        "llm_api_key": "test-key",
        "access_user_id": user_id,
        "access_project_id": None,
    }

    persisted = await db.scalar(
        select(WorkflowRun).where(WorkflowRun.id == result.workflow_run.id)
    )
    steps = (
        await db.execute(
            select(StepRun)
            .where(StepRun.workflow_run_id == result.workflow_run.id)
            .order_by(StepRun.created_at)
        )
    ).scalars().all()
    step_payloads = {step.step_id: step.output_payload for step in steps}

    assert persisted is not None
    assert persisted.output_payload == output_payload
    assert step_payloads["retrieve"] == {
        "name": "retrieve",
        "status": "completed",
        "summary": "Retrieved reviewer context",
    }
    assert step_payloads["format_output"] == {
        "name": "format_output",
        "status": "completed",
        "summary": "Formatted response",
    }
    assert result.trace_payload == trace_payload
    assert result.legacy_steps == [
        {
            "name": "retrieve",
            "status": "completed",
            "summary": "Retrieved reviewer context",
        },
        {
            "name": "format_output",
            "status": "completed",
            "summary": "Formatted response",
        },
    ]


async def test_run_workflow_definition_marks_failed_run(db: AsyncSession):
    session_id, user_id = await _create_workflow_test_session(db)
    workflow = get_workflow_definition("reviewer_assistant")

    async def failing_runner(**_kwargs):
        raise RuntimeError("synthetic failure")

    with pytest.raises(WorkflowExecutionError) as exc_info:
        await run_workflow_definition(
            workflow=workflow,
            session_id=session_id,
            user_id=user_id,
            source_ids=[],
            input_payload={"review_comments": "Please address novelty concerns."},
            db=db,
            llm_model=None,
            llm_api_base=None,
            llm_api_key=None,
            legacy_agent_runner=failing_runner,
        )

    assert isinstance(exc_info.value.original_error, RuntimeError)
    assert exc_info.value.__cause__ is exc_info.value.original_error

    failed_run = await db.scalar(
        select(WorkflowRun).order_by(WorkflowRun.created_at.desc())
    )
    assert failed_run is not None
    assert exc_info.value.workflow_run_id == failed_run.id
    assert failed_run.status == "failed"
    assert failed_run.error_message == "Workflow execution failed."

    steps = (
        await db.execute(
            select(StepRun)
            .where(StepRun.workflow_run_id == failed_run.id)
            .order_by(StepRun.created_at)
        )
    ).scalars().all()
    failed_steps = [step for step in steps if step.status == "failed"]
    assert failed_steps
    assert failed_steps[0].error_message == "Workflow step failed."
