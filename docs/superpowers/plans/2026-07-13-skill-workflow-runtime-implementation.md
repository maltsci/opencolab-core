# Skill + Workflow Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a v1 skill and workflow runtime that records `WorkflowRun` and `StepRun` state, exposes workflow APIs, and lets the existing agent API delegate to the new runtime without breaking current behavior.

**Architecture:** Keep the first implementation synchronous and backend-owned. Add registry-driven built-in skill/workflow definitions, persistent run models, a linear workflow executor, workflow APIs, and a compatibility bridge from the existing `/api/v1/agents` routes. Reuse current RAG, LLM, trace, citation, `AgentRun`, and research-memory writeback behavior rather than introducing a second agent stack.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic v2, pytest, existing LiteLLM service, existing RAG service, React/TypeScript only for minimal run-step display if needed after backend compatibility is stable.

---

## File Map

### Backend files to create

- `backend/app/models/workflow_run.py`
  - SQLAlchemy `WorkflowRun` and `StepRun` models.
- `backend/app/schemas/skill.py`
  - Pydantic skill definition response schemas.
- `backend/app/schemas/workflow.py`
  - Pydantic workflow definition, run, step, and run-create schemas.
- `backend/app/skills/__init__.py`
  - skill package exports.
- `backend/app/skills/builtin.py`
  - built-in skill definitions and skill handlers.
- `backend/app/skills/registry.py`
  - built-in skill registry and lookup errors.
- `backend/app/workflows/__init__.py`
  - workflow package exports.
- `backend/app/workflows/builtin.py`
  - built-in workflow definitions for the current two agents.
- `backend/app/workflows/registry.py`
  - built-in workflow registry and lookup errors.
- `backend/app/workflows/executor.py`
  - linear workflow execution and step persistence.
- `backend/app/api/skills.py`
  - read-only skill APIs.
- `backend/app/api/workflows.py`
  - workflow list, run, get, steps, cancel, and save-memory APIs.
- `backend/alembic/versions/b8c9d0e1f2a3_add_workflow_runs.py`
  - migration for `workflow_runs`, `step_runs`, and `agent_runs.workflow_run_id`.
- `tests/test_workflow_runtime.py`
  - registry, executor, model, and failure tests.
- `tests/test_workflows_api.py`
  - workflow API and memory writeback tests.

### Backend files to modify

- `backend/app/models/__init__.py`
  - export `WorkflowRun` and `StepRun`.
- `backend/app/models/agent_run.py`
  - add nullable `workflow_run_id` relationship.
- `backend/app/models/trace.py`
  - add nullable `workflow_run_id` relationship so workflow-native runs can own traces without an `AgentRun`.
- `backend/app/schemas/agent.py`
  - add optional `workflow_run_id`; map steps from `StepRun` when loaded.
- `backend/app/api/agents.py`
  - make `/agents/run` call the workflow runtime while preserving response shape.
- `backend/app/main.py`
  - register `skills_router` and `workflows_router`.
- `tests/test_agent_runtime.py`
  - keep current direct legacy agent tests where useful; add compatibility assertions.
- `tests/test_agents_api.py`
  - verify agent API creates and returns a linked `WorkflowRun`.

### Frontend files to modify only if backend API compatibility is not enough

- `frontend/src/types/agent.ts`
  - add optional `workflow_run_id`.
- `frontend/src/types/workflow.ts`
  - add workflow response types if a step panel is included in v1.
- `frontend/src/pages/Session.tsx`
  - keep current agent UX; optionally link to workflow step details.

## Task 1: Add workflow persistence models and migration

**Files:**
- Create: `backend/app/models/workflow_run.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/agent_run.py`
- Modify: `backend/app/models/trace.py`
- Create: `backend/alembic/versions/b8c9d0e1f2a3_add_workflow_runs.py`
- Test: `tests/test_workflow_runtime.py`

- [ ] **Step 1: Write failing table-registration test**

Add `tests/test_workflow_runtime.py`:

```python
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base


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
```

- [ ] **Step 2: Run the failing test**

Run: `pytest tests/test_workflow_runtime.py::test_workflow_tables_are_registered -v`

Expected: FAIL because the workflow models and columns do not exist yet.

- [ ] **Step 3: Add SQLAlchemy models**

Create `backend/app/models/workflow_run.py` with:

```python
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workflow_id: Mapped[str] = mapped_column(String(100), index=True)
    workflow_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="pending", server_default="pending", index=True
    )
    input_payload: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    output_payload: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by_type: Mapped[str] = mapped_column(
        String(32), default="human", server_default="human"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    session: Mapped["Session"] = relationship()
    steps: Mapped[list["StepRun"]] = relationship(
        back_populates="workflow_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="StepRun.created_at",
    )


class StepRun(Base):
    __tablename__ = "step_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workflow_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[str] = mapped_column(String(100), index=True)
    step_type: Mapped[str] = mapped_column(String(32))
    ref: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(
        String(32), default="pending", server_default="pending", index=True
    )
    input_payload: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    output_payload: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    workflow_run: Mapped["WorkflowRun"] = relationship(back_populates="steps")
```

- [ ] **Step 4: Export models**

Modify `backend/app/models/__init__.py`:

```python
from app.models.workflow_run import StepRun, WorkflowRun
```

and include both names in `__all__`.

- [ ] **Step 5: Link existing records**

Modify `backend/app/models/agent_run.py`:

```python
    workflow_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workflow_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    workflow_run: Mapped["WorkflowRun | None"] = relationship()
```

Modify `backend/app/models/trace.py`:

```python
    workflow_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    workflow_run: Mapped["WorkflowRun | None"] = relationship()
```

- [ ] **Step 6: Add Alembic migration**

Create `backend/alembic/versions/b8c9d0e1f2a3_add_workflow_runs.py` with revision id `b8c9d0e1f2a3` and `down_revision = "a7d3e9c4b2f1"`. If the current repository head changes before execution, run `cd backend && .venv/bin/alembic heads` and set `down_revision` to the single current head.

The migration must:

- create `workflow_runs`
- create indexes on `workflow_runs.session_id`, `workflow_runs.workflow_id`, `workflow_runs.status`, `workflow_runs.created_by`
- create `step_runs`
- create indexes on `step_runs.workflow_run_id`, `step_runs.step_id`, `step_runs.status`
- add nullable `agent_runs.workflow_run_id`
- add nullable `research_traces.workflow_run_id`
- create indexes for both new nullable columns

- [ ] **Step 7: Run focused verification**

Run: `pytest tests/test_workflow_runtime.py::test_workflow_tables_are_registered -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/workflow_run.py backend/app/models/__init__.py backend/app/models/agent_run.py backend/app/models/trace.py backend/alembic/versions/b8c9d0e1f2a3_add_workflow_runs.py tests/test_workflow_runtime.py
git commit -m "feat: add workflow run persistence"
```

## Task 2: Add skill and workflow definition schemas plus registries

**Files:**
- Create: `backend/app/schemas/skill.py`
- Create: `backend/app/schemas/workflow.py`
- Create: `backend/app/skills/__init__.py`
- Create: `backend/app/skills/builtin.py`
- Create: `backend/app/skills/registry.py`
- Create: `backend/app/workflows/__init__.py`
- Create: `backend/app/workflows/builtin.py`
- Create: `backend/app/workflows/registry.py`
- Test: `tests/test_workflow_runtime.py`

- [ ] **Step 1: Add failing registry tests**

Append to `tests/test_workflow_runtime.py`:

```python
from app.skills.registry import get_skill_definition, list_skill_definitions
from app.workflows.registry import get_workflow_definition, list_workflow_definitions


def test_builtin_skill_registry_contains_expected_skills():
    skill_ids = {skill.id for skill in list_skill_definitions()}

    assert "rag-retrieve" in skill_ids
    assert "literature-synthesize" in skill_ids
    assert "grounding-validate" in skill_ids
    assert get_skill_definition("rag-retrieve").name == "RAG Retrieve"


def test_builtin_workflow_registry_contains_current_agents():
    workflow_ids = {workflow.id for workflow in list_workflow_definitions()}

    assert "literature_synthesizer" in workflow_ids
    assert "reviewer_assistant" in workflow_ids
    assert get_workflow_definition("literature_synthesizer").steps[0].id == "retrieve"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow_runtime.py -k "registry_contains" -v`

Expected: FAIL because the packages and schemas do not exist yet.

- [ ] **Step 3: Add skill schemas**

Create `backend/app/schemas/skill.py`:

```python
from typing import Any, Literal

from pydantic import BaseModel, Field


class SkillDefinition(BaseModel):
    id: str
    version: int = 1
    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    tools: list[str] = Field(default_factory=list)
    step_template: dict[str, Any] = Field(default_factory=dict)
    validation_rules: list[str] = Field(default_factory=list)
    writeback_policy: dict[str, Any] = Field(default_factory=dict)


SkillStepType = Literal["skill", "llm", "tool", "human_checkpoint"]
```

- [ ] **Step 4: Add workflow schemas**

Create `backend/app/schemas/workflow.py` with:

```python
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.skill import SkillStepType


WorkflowRunStatus = Literal[
    "pending",
    "running",
    "waiting_for_checkpoint",
    "completed",
    "failed",
    "cancelled",
]


class WorkflowStepDefinition(BaseModel):
    id: str
    type: SkillStepType
    ref: str
    depends_on: list[str] = Field(default_factory=list)
    retry_policy: dict[str, Any] = Field(default_factory=dict)
    validation_rule: str | None = None
    output_key: str


class WorkflowDefinition(BaseModel):
    id: str
    version: int = 1
    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    steps: list[WorkflowStepDefinition]
    checkpoint_policy: dict[str, Any] = Field(default_factory=dict)
    writeback_policy: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_unique_step_ids(self) -> "WorkflowDefinition":
        step_ids = [step.id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("workflow step ids must be unique")
        return self


class WorkflowRunCreateRequest(BaseModel):
    session_id: str
    input: dict[str, Any] = Field(default_factory=dict)


class StepRunResponse(BaseModel):
    id: str
    workflow_run_id: str
    step_id: str
    step_type: str
    ref: str
    status: str
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_payload: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    attempt_count: int
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}


class WorkflowRunResponse(BaseModel):
    id: str
    workflow_id: str
    workflow_version: int
    session_id: str
    status: str
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_payload: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    created_by: str | None = None
    created_by_type: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
```

- [ ] **Step 5: Add built-in skill definitions**

Create `backend/app/skills/builtin.py` with data-only definitions for:

- `rag-retrieve`
- `literature-synthesize`
- `reviewer-response-draft`
- `grounding-validate`
- `format-output`

Each definition must use `SkillDefinition` and include a short English description.

- [ ] **Step 6: Add built-in workflow definitions**

Create `backend/app/workflows/builtin.py` with two `WorkflowDefinition` values:

- `literature_synthesizer`
- `reviewer_assistant`

Use the same ids as the current `AgentName` literal so the agent compatibility layer does not need a name translation table.

The `literature_synthesizer` steps must be:

```python
[
    WorkflowStepDefinition(id="retrieve", type="skill", ref="rag-retrieve", output_key="retrieved_chunks"),
    WorkflowStepDefinition(id="synthesize", type="skill", ref="literature-synthesize", depends_on=["retrieve"], output_key="synthesis"),
    WorkflowStepDefinition(id="validate", type="skill", ref="grounding-validate", depends_on=["synthesize"], output_key="validation"),
    WorkflowStepDefinition(id="format_output", type="skill", ref="format-output", depends_on=["validate"], output_key="final_output"),
]
```

The `reviewer_assistant` steps must use the same retrieve, draft, validate, and format shape, with `ref="reviewer-response-draft"` for the draft step.

- [ ] **Step 7: Add registries**

Create `backend/app/skills/registry.py` and `backend/app/workflows/registry.py` with:

- module-level dictionaries keyed by `id`
- `list_*_definitions()`
- `get_*_definition(id: str)`
- `UnknownSkillError` and `UnknownWorkflowError`
- duplicate id protection during registry construction

- [ ] **Step 8: Run registry tests**

Run: `pytest tests/test_workflow_runtime.py -k "registry_contains" -v`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/app/schemas/skill.py backend/app/schemas/workflow.py backend/app/skills backend/app/workflows tests/test_workflow_runtime.py
git commit -m "feat: add workflow definition registries"
```

## Task 3: Build the linear workflow executor

**Files:**
- Create: `backend/app/workflows/executor.py`
- Modify: `tests/test_workflow_runtime.py`

- [ ] **Step 1: Add failing executor success test**

Append to `tests/test_workflow_runtime.py`:

```python
from sqlalchemy import select

from app.models.workflow_run import StepRun, WorkflowRun
from app.workflows.executor import run_workflow_definition
from app.workflows.registry import get_workflow_definition


async def test_run_workflow_definition_persists_step_runs(db: AsyncSession):
    workflow = get_workflow_definition("reviewer_assistant")

    result = await run_workflow_definition(
        workflow=workflow,
        session_id="session-1",
        user_id="user-1",
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

    assert persisted is not None
    assert persisted.status == "completed"
    assert [step.step_id for step in steps] == [
        "retrieve",
        "draft_response",
        "validate",
        "format_output",
    ]
    assert result.output["agent"] == "reviewer_assistant"
```

- [ ] **Step 2: Run the failing test**

Run: `pytest tests/test_workflow_runtime.py::test_run_workflow_definition_persists_step_runs -v`

Expected: FAIL because the executor does not exist.

- [ ] **Step 3: Add executor result type and function**

Create `backend/app/workflows/executor.py`:

```python
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

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
    ) -> AgentExecutionResult:
        raise NotImplementedError


@dataclass(slots=True)
class WorkflowExecutionResult:
    workflow_run: WorkflowRun
    steps: list[StepRun]
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
            output = {
                "agent": workflow.id,
                "input": input_payload,
            }
            trace_payload = {
                "inputs": input_payload,
                "retrieval": [],
                "citations": [],
                "summary_steps": [],
            }
        else:
            execution = await legacy_agent_runner(
                agent_name=workflow.id,
                source_ids=source_ids,
                agent_input=input_payload,
                db=db,
                llm_model=llm_model,
                llm_api_base=llm_api_base,
                llm_api_key=llm_api_key,
            )
            output = execution["output"]
            trace_payload = execution["trace_payload"]
            legacy_step_records = execution["steps"]

        legacy_steps = {item["name"]: item for item in legacy_step_records}
        for step_run in step_runs:
            step_run.status = "completed"
            step_run.attempt_count = 1
            step_run.started_at = now
            step_run.finished_at = datetime.now(UTC)
            matching_step = legacy_steps.get(step_run.step_id)
            step_run.output_payload = matching_step or {}

        workflow_run.status = "completed"
        workflow_run.output_payload = output
        workflow_run.finished_at = datetime.now(UTC)
        await db.flush()
        return WorkflowExecutionResult(
            workflow_run=workflow_run,
            steps=step_runs,
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
        raise exc
```

- [ ] **Step 4: Run executor success test**

Run: `pytest tests/test_workflow_runtime.py::test_run_workflow_definition_persists_step_runs -v`

Expected: PASS.

- [ ] **Step 5: Add failure test**

Append:

```python
async def test_run_workflow_definition_marks_failed_run(db: AsyncSession):
    workflow = get_workflow_definition("reviewer_assistant")

    async def failing_runner(**_kwargs):
        raise RuntimeError("synthetic failure")

    with pytest.raises(RuntimeError):
        await run_workflow_definition(
            workflow=workflow,
            session_id="session-1",
            user_id="user-1",
            source_ids=[],
            input_payload={"review_comments": "Please address novelty concerns."},
            db=db,
            llm_model=None,
            llm_api_base=None,
            llm_api_key=None,
            legacy_agent_runner=failing_runner,
        )

    failed_run = await db.scalar(
        select(WorkflowRun).order_by(WorkflowRun.created_at.desc())
    )
    assert failed_run is not None
    assert failed_run.status == "failed"
    assert failed_run.error_message == "Workflow execution failed."
```

- [ ] **Step 6: Run focused runtime tests**

Run: `pytest tests/test_workflow_runtime.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/workflows/executor.py tests/test_workflow_runtime.py
git commit -m "feat: execute built-in workflows"
```

## Task 4: Add skill and workflow read/run APIs

**Files:**
- Create: `backend/app/api/skills.py`
- Create: `backend/app/api/workflows.py`
- Modify: `backend/app/main.py`
- Create: `tests/test_workflows_api.py`

- [ ] **Step 1: Add failing API tests**

Create `tests/test_workflows_api.py`:

```python
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow_run import StepRun, WorkflowRun

pytestmark = pytest.mark.asyncio


async def _create_session(client: AsyncClient, headers: dict) -> str:
    response = await client.post(
        "/api/v1/sessions",
        json={"title": "Workflow API Session"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


async def test_list_builtin_workflows(client: AsyncClient, researcher_headers: dict):
    response = await client.get("/api/v1/workflows", headers=researcher_headers)

    assert response.status_code == 200
    workflow_ids = {item["id"] for item in response.json()}
    assert "literature_synthesizer" in workflow_ids
    assert "reviewer_assistant" in workflow_ids


async def test_run_builtin_workflow_creates_run_and_steps(
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
        await db.execute(
            select(StepRun).where(StepRun.workflow_run_id == payload["id"])
        )
    ).scalars().all()
    assert len(steps) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflows_api.py -v`

Expected: FAIL because the routers do not exist.

- [ ] **Step 3: Add skill router**

Create `backend/app/api/skills.py`:

```python
from fastapi import APIRouter, HTTPException

from app.schemas.skill import SkillDefinition
from app.skills.registry import UnknownSkillError, get_skill_definition, list_skill_definitions

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("", response_model=list[SkillDefinition])
async def list_skills():
    return list_skill_definitions()


@router.get("/{skill_id}", response_model=SkillDefinition)
async def get_skill(skill_id: str):
    try:
        return get_skill_definition(skill_id)
    except UnknownSkillError as exc:
        raise HTTPException(status_code=404, detail="Skill not found") from exc
```

- [ ] **Step 4: Add workflow router**

Create `backend/app/api/workflows.py` with routes:

- `GET /workflows`
- `GET /workflows/{workflow_id}`
- `POST /workflows/{workflow_id}/run`
- `GET /workflow-runs/{run_id}`
- `GET /workflow-runs/{run_id}/steps`
- `POST /workflow-runs/{run_id}/cancel`

The run route must:

- verify session ownership using `_get_session_for_user`
- resolve workflow via `get_workflow_definition`
- get runtime LLM config through `get_runtime_value` and `get_runtime_llm_api_key`
- read `source_ids` from `body.input.get("source_ids", [])` only when it is a list
- expand source groups using `expand_source_ids_for_rag`
- call `run_workflow_definition`
- pass `run_agent_definition` as `legacy_agent_runner`
- create a `ResearchTrace` linked to `workflow_run_id`
- return `WorkflowRunResponse`

- [ ] **Step 5: Register routers**

Modify `backend/app/main.py`:

```python
from app.api.skills import router as skills_router
from app.api.workflows import router as workflows_router
```

and include:

```python
app.include_router(skills_router, prefix=api)
app.include_router(workflows_router, prefix=api)
```

- [ ] **Step 6: Run API tests**

Run: `pytest tests/test_workflows_api.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/skills.py backend/app/api/workflows.py backend/app/main.py tests/test_workflows_api.py
git commit -m "feat: add workflow APIs"
```

## Task 5: Make the existing agent API delegate to workflow runtime

**Files:**
- Modify: `backend/app/schemas/agent.py`
- Modify: `backend/app/api/agents.py`
- Modify: `tests/test_agents_api.py`
- Modify: `tests/test_agent_runtime.py`

- [ ] **Step 1: Add failing compatibility test**

Append to `tests/test_agents_api.py`:

```python
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
```

- [ ] **Step 2: Run the failing test**

Run: `pytest tests/test_agents_api.py::test_run_agent_creates_linked_workflow_run -v`

Expected: FAIL because `AgentRunResponse` does not expose `workflow_run_id` and `/agents/run` still owns execution directly.

- [ ] **Step 3: Extend agent response schema**

Modify `backend/app/schemas/agent.py`:

```python
    workflow_run_id: str | None = None
```

Ensure `resolve_trace_payload` includes:

```python
"workflow_run_id": getattr(data, "workflow_run_id", None),
```

in the ORM-style conversion path.

- [ ] **Step 4: Refactor `/agents/run`**

Modify `backend/app/api/agents.py` so it:

- validates session and sources as it does now
- creates `AgentRun(status="running")` before execution
- resolves the workflow with `get_workflow_definition(body.agent)`
- calls `run_workflow_definition` with `legacy_agent_runner=run_agent_definition`
- sets `agent_run.workflow_run_id`
- copies `workflow_execution.output` into `agent_run.output_json`
- copies step summaries from `workflow_execution.steps` into `agent_run.steps_json`
- creates the assistant `Message`
- creates `ResearchTrace` with both `agent_run_id` and `workflow_run_id`
- returns the existing `AgentRunResponse`

Keep existing `UnknownAgentError` behavior by translating unknown workflow or unknown agent to the same `400` response text used today.

- [ ] **Step 5: Keep message refresh behavior**

Run: `pytest tests/test_agents_api.py::test_run_agent_persists_assistant_message_for_refresh -v`

Expected: PASS.

- [ ] **Step 6: Run compatibility tests**

Run: `pytest tests/test_agents_api.py tests/test_agent_runtime.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/agent.py backend/app/api/agents.py tests/test_agents_api.py tests/test_agent_runtime.py
git commit -m "feat: route agents through workflow runtime"
```

## Task 6: Add workflow-native memory writeback

**Files:**
- Modify: `backend/app/schemas/workflow.py`
- Modify: `backend/app/api/workflows.py`
- Modify: `tests/test_workflows_api.py`

- [ ] **Step 1: Add failing workflow memory tests**

Append to `tests/test_workflows_api.py`:

```python
async def test_save_workflow_run_to_memory_creates_research_object(
    client: AsyncClient,
    researcher_headers: dict,
    db: AsyncSession,
    monkeypatch,
):
    session_id = await _create_session(client, researcher_headers)

    async def fake_runner(**_kwargs):
        return {
            "output": {"agent": "reviewer_assistant", "summary": "Address concerns"},
            "steps": [{"name": "format_output", "status": "completed", "summary": "formatted"}],
            "trace_payload": {
                "inputs": {"review_comments": "Please address novelty."},
                "retrieval": [],
                "citations": [{"source_id": "source-1", "chunk_id": "chunk-1", "snippet": "support"}],
                "summary_steps": ["formatted"],
            },
        }

    monkeypatch.setattr("app.api.workflows.run_agent_definition", fake_runner)

    run_response = await client.post(
        "/api/v1/workflows/reviewer_assistant/run",
        headers=researcher_headers,
        json={"session_id": session_id, "input": {"review_comments": "Please address novelty."}},
    )
    run_id = run_response.json()["id"]

    response = await client.post(
        f"/api/v1/workflow-runs/{run_id}/save-memory",
        headers=researcher_headers,
        json={
            "type": "discussion",
            "title": "Reviewer strategy",
            "content": "Address concerns",
            "relation": {"enabled": False},
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["research_object"]["type"] == "discussion"
    assert payload["research_object"]["session_id"] == session_id
```

- [ ] **Step 2: Run failing test**

Run: `pytest tests/test_workflows_api.py::test_save_workflow_run_to_memory_creates_research_object -v`

Expected: FAIL because the workflow-native save route does not exist.

- [ ] **Step 3: Add request and response schemas**

In `backend/app/schemas/workflow.py`, mirror the existing agent save-memory request and response:

```python
class WorkflowRunSaveMemoryRelationRequest(BaseModel):
    enabled: bool = False
    relation_type: ResearchRelationType | None = None
    target_object_id: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def validate_when_enabled(self) -> "WorkflowRunSaveMemoryRelationRequest":
        if self.enabled and (self.relation_type is None or not self.target_object_id):
            raise ValueError("relation_type and target_object_id are required when relation is enabled")
        return self


class WorkflowRunSaveMemoryRequest(BaseModel):
    type: Literal["hypothesis", "discussion"]
    title: str | None = Field(default=None, max_length=500)
    content: str
    relation: WorkflowRunSaveMemoryRelationRequest = Field(
        default_factory=WorkflowRunSaveMemoryRelationRequest
    )


class WorkflowRunSaveMemoryResponse(BaseModel):
    research_object: ResearchObjectResponse
    relation: ResearchObjectRelationResponse | None = None
```

- [ ] **Step 4: Implement save route**

In `backend/app/api/workflows.py`, add:

```python
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
    await _get_session_for_user(workflow_run.session_id, user, db)
    if workflow_run.status != "completed":
        raise HTTPException(status_code=400, detail="Workflow run must be completed")
    return await _save_workflow_run_memory_objects(
        workflow_run=workflow_run,
        body=body,
        user=user,
        db=db,
    )
```

Behavior:

- load `WorkflowRun` by id and `created_by == user.id`
- verify session ownership
- reject non-completed runs with `400`
- select latest `ResearchTrace` linked by `workflow_run_id`
- create `ResearchObject` with `origin = "workflow_run"`
- optionally create one `ResearchObjectRelation`
- use the same evidence shape as the existing agent save-memory route
- translate duplicate relation `IntegrityError` into `409`

Move shared helper functions from `backend/app/api/agents.py` into a small shared module only if direct duplication grows beyond the two response builders already present. Keep this task focused.

- [ ] **Step 5: Run workflow memory tests**

Run: `pytest tests/test_workflows_api.py -k "save_workflow_run_to_memory" -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/workflow.py backend/app/api/workflows.py tests/test_workflows_api.py
git commit -m "feat: save workflow runs to memory"
```

## Task 7: Add minimal frontend type compatibility and run full checks

**Files:**
- Modify: `frontend/src/types/agent.ts`
- Create: `frontend/src/types/workflow.ts`

- [ ] **Step 1: Add frontend agent compatibility type**

In `frontend/src/types/agent.ts`, add:

```typescript
workflow_run_id?: string | null;
```

to the existing agent run response interface.

- [ ] **Step 2: Add workflow types**

Create `frontend/src/types/workflow.ts`:

```typescript
export interface WorkflowDefinition {
  id: string;
  version: number;
  name: string;
  description: string;
}

export interface WorkflowRunResponse {
  id: string;
  workflow_id: string;
  workflow_version: number;
  session_id: string;
  status: string;
  input_payload: Record<string, unknown>;
  output_payload: Record<string, unknown>;
  error_message?: string | null;
  created_by?: string | null;
  created_by_type: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface StepRunResponse {
  id: string;
  workflow_run_id: string;
  step_id: string;
  step_type: string;
  ref: string;
  status: string;
  input_payload: Record<string, unknown>;
  output_payload: Record<string, unknown>;
  error_message?: string | null;
  attempt_count: number;
  started_at?: string | null;
  finished_at?: string | null;
}
```

- [ ] **Step 3: Run frontend build**

Run: `cd frontend && npm run build`

Expected: PASS.

- [ ] **Step 4: Run focused backend tests**

Run: `pytest tests/test_workflow_runtime.py tests/test_workflows_api.py tests/test_agents_api.py tests/test_agent_runtime.py -v`

Expected: PASS.

- [ ] **Step 5: Run full backend test suite**

Run: `pytest -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/agent.ts frontend/src/types/workflow.ts
git commit -m "feat: add workflow frontend types"
```

## Final Verification

- [ ] **Step 1: Check migration heads**

Run: `cd backend && .venv/bin/alembic heads`

Expected: one head. If there is more than one head, add a merge migration before merging the branch.

- [ ] **Step 2: Run backend tests**

Run: `pytest -v`

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run: `cd frontend && npm run build`

Expected: PASS.

- [ ] **Step 4: Inspect git status**

Run: `git status --short`

Expected: no unstaged implementation files after the final commit.

## Execution Notes

- Keep v1 workflow execution linear even though workflow definitions include `depends_on`.
- Do not introduce arbitrary Python, shell, or user-installed tool execution.
- Do not remove existing `AgentRun` fields; they are compatibility storage for old rows and current UI.
- Do not add admin editing pages for skills or workflows in this iteration.
- Keep all user-facing frontend strings in `frontend/src/locales/en-US.json` and `frontend/src/locales/zh-CN.json`.
- Keep code comments and internal log/error text in English.
