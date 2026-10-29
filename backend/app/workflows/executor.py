from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session
from app.models.workflow_run import StepRun, WorkflowRun
from app.schemas.workflow import WorkflowDefinition
from app.services.agents.base import AgentExecutionResult


class LegacyAgentRunner(Protocol):
    async def __call__(
        self,
        *,
        agent_name: str,
        source_ids: list[str],
        agent_input: dict[str, Any],
        db: AsyncSession,
        llm_model: str | None,
        llm_api_base: str | None,
        llm_api_key: str | None,
        access_user_id: str | None,
        access_project_id: str | None,
        access_agent_run_id: str | None,
    ) -> AgentExecutionResult:
        raise NotImplementedError


class WorkflowExecutionError(RuntimeError):
    def __init__(self, workflow_run_id: str, original_error: Exception) -> None:
        super().__init__("Workflow execution failed.")
        self.workflow_run_id = workflow_run_id
        self.original_error = original_error


@dataclass(slots=True)
class WorkflowExecutionResult:
    workflow_run: WorkflowRun
    steps: list[StepRun]
    legacy_steps: list[dict[str, Any]]
    output: dict[str, Any]
    trace_payload: dict[str, Any]


async def run_workflow_definition(
    *,
    workflow: WorkflowDefinition,
    session_id: str,
    user_id: str,
    source_ids: list[str],
    input_payload: dict[str, Any],
    db: AsyncSession,
    llm_model: str | None,
    llm_api_base: str | None,
    llm_api_key: str | None,
    legacy_agent_runner: LegacyAgentRunner | None,
) -> WorkflowExecutionResult:
    """Run a built-in workflow and flush persisted run state.

    The caller owns transaction commit or rollback; this executor never commits.
    On failure, it flushes failed workflow and step statuses before raising a
    WorkflowExecutionError that carries the failed workflow run id. Callers that
    need failed audit state persisted must commit after catching the exception.
    """
    now = datetime.now(UTC)
    workflow_run = WorkflowRun(
        workflow_id=workflow.id,
        workflow_version=workflow.version,
        session_id=session_id,
        status="running",
        input_payload=input_payload,
        created_by=user_id,
        created_by_type="human",
        started_at=now,
    )
    db.add(workflow_run)
    await db.flush()

    step_runs = [
        StepRun(
            workflow_run_id=workflow_run.id,
            step_id=step.id,
            step_type=step.type,
            ref=step.ref,
            status="pending",
            input_payload={},
        )
        for step in workflow.steps
    ]
    db.add_all(step_runs)
    await db.flush()

    try:
        legacy_step_records: list[dict[str, Any]] = []
        if legacy_agent_runner is None:
            output: dict[str, Any] = {
                "agent": workflow.id,
                "input": input_payload,
            }
            trace_payload: dict[str, Any] = {
                "inputs": input_payload,
                "retrieval": [],
                "citations": [],
                "summary_steps": [],
            }
        else:
            session = await db.get(Session, session_id)
            execution = await legacy_agent_runner(
                agent_name=workflow.id,
                source_ids=source_ids,
                agent_input=input_payload,
                db=db,
                llm_model=llm_model,
                llm_api_base=llm_api_base,
                llm_api_key=llm_api_key,
                access_user_id=user_id,
                access_project_id=session.project_id if session else None,
                access_agent_run_id=f"workflow:{workflow_run.id}",
            )
            output = execution["output"]
            trace_payload = execution["trace_payload"]
            legacy_step_records = execution["steps"]

        legacy_steps = {item["name"]: item for item in legacy_step_records}
        for step_run in step_runs:
            step_started_at = datetime.now(UTC)
            step_run.status = "completed"
            step_run.attempt_count = 1
            step_run.started_at = step_started_at
            step_run.finished_at = datetime.now(UTC)
            step_run.output_payload = legacy_steps.get(step_run.step_id) or {
                "name": step_run.step_id,
                "status": "completed",
                "summary": f"Executed step ref: {step_run.ref}",
            }

        workflow_run.status = "completed"
        workflow_run.output_payload = output
        workflow_run.finished_at = datetime.now(UTC)
        await db.flush()
        return WorkflowExecutionResult(
            workflow_run=workflow_run,
            steps=step_runs,
            legacy_steps=legacy_step_records,
            output=output,
            trace_payload=trace_payload,
        )
    except Exception as exc:
        workflow_run.status = "failed"
        workflow_run.error_message = "Workflow execution failed."
        workflow_run.finished_at = datetime.now(UTC)
        pending_or_running = next(
            (step for step in step_runs if step.status in {"pending", "running"}),
            None,
        )
        if pending_or_running is not None:
            pending_or_running.status = "failed"
            pending_or_running.error_message = "Workflow step failed."
            pending_or_running.finished_at = datetime.now(UTC)
        await db.flush()
        raise WorkflowExecutionError(workflow_run.id, exc) from exc
