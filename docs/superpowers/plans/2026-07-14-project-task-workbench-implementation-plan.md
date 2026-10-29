# Project Task Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reframe OpenColab around project-scoped user-facing tasks by introducing `TaskDefinition`, a project home with a large prompt plus recommended tasks, and a chat-style task workspace that runs existing workflows without exposing skill/workflow complexity to ordinary researchers.

**Architecture:** Add a product-layer `TaskDefinition` object that wraps `WorkflowDefinition` for researcher-facing use. Keep the current workflow runtime and research memory model, but move skills and workflows behind admin-only surfaces. Build a new researcher-first launch path from project page to task workspace, while preserving legacy sessions during transition.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, React, TypeScript, Ant Design, React Router, React Query-compatible existing data flow, i18n JSON locale files, pytest, Vite.

---

## Scope guard

This plan intentionally targets the first usable end-to-end version of the task workbench.

In scope:

- `TaskDefinition` persistence and APIs
- project-level task availability
- researcher-facing project home entry
- chat-style task workspace
- task-to-workflow execution handoff
- admin task publishing UI

Out of scope for this plan:

- full internet skill marketplace
- one-click external skill install
- autonomous task auto-routing without user confirmation
- replacing all existing session flows at once
- visual workflow builder redesign

## File map

### Backend

- Create: `backend/app/models/task_definition.py`
- Create: `backend/alembic/versions/<timestamp>_add_task_definitions.py`
- Create: `backend/app/schemas/task.py`
- Create: `backend/app/api/tasks.py`
- Create: `backend/app/services/task_service.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/api/admin.py`
- Modify: `backend/app/api/sessions.py`
- Modify: `backend/app/api/workflows.py`
- Modify: `backend/app/main.py`

### Frontend

- Create: `frontend/src/types/task.ts`
- Create: `frontend/src/pages/TaskWorkspace.tsx`
- Create: `frontend/src/components/tasks/TaskComposer.tsx`
- Create: `frontend/src/components/tasks/TaskCard.tsx`
- Create: `frontend/src/components/tasks/TaskSidebar.tsx`
- Modify: `frontend/src/pages/Home.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/admin/Workflows.tsx`
- Create or Modify: `frontend/src/pages/admin/Tasks.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`

### Tests

- Create: `tests/test_tasks_api.py`
- Modify: `tests/test_workflows_api.py`
- Add frontend verification via `npm run build`

---

### Task 1: Add backend `TaskDefinition` model and migration

**Files:**
- Create: `backend/app/models/task_definition.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/<timestamp>_add_task_definitions.py`
- Test: `tests/test_tasks_api.py`

- [ ] **Step 1: Write the failing API test for listing published tasks**

Add a first failing test in `tests/test_tasks_api.py` that expects authenticated users to read an empty task list from `/api/v1/tasks`.

```python
import pytest

pytestmark = pytest.mark.asyncio


async def test_list_tasks_returns_empty_list_initially(client, researcher_headers):
    response = await client.get("/api/v1/tasks", headers=researcher_headers)

    assert response.status_code == 200
    assert response.json() == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
backend/.venv/bin/pytest tests/test_tasks_api.py::test_list_tasks_returns_empty_list_initially -v
```

Expected: FAIL with missing route or import errors for task APIs.

- [ ] **Step 3: Add the SQLAlchemy model**

Create `backend/app/models/task_definition.py` with a minimal persisted wrapper around workflows.

```python
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TaskDefinitionRecord(Base):
    __tablename__ = "task_definitions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    workflow_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    input_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    starter_prompts: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    project_context_policy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result_presentation: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
```

- [ ] **Step 4: Export the model**

Update `backend/app/models/__init__.py` to export `TaskDefinitionRecord`.

```python
from app.models.task_definition import TaskDefinitionRecord
```

- [ ] **Step 5: Add the migration**

Create an Alembic migration that creates `task_definitions` with the fields above and an index on `workflow_id`.

- [ ] **Step 6: Run the backend test again**

Run:

```bash
backend/.venv/bin/pytest tests/test_tasks_api.py::test_list_tasks_returns_empty_list_initially -v
```

Expected: still FAIL, now due to missing schema/route rather than missing model.

---

### Task 2: Add task schemas, service, and public/admin APIs

**Files:**
- Create: `backend/app/schemas/task.py`
- Create: `backend/app/services/task_service.py`
- Create: `backend/app/api/tasks.py`
- Modify: `backend/app/api/admin.py`
- Modify: `backend/app/main.py`
- Test: `tests/test_tasks_api.py`

- [ ] **Step 1: Extend the failing test to cover admin create and public list**

Add a failing test that creates a task via admin and then lists it publicly.

```python
async def test_admin_can_create_task_and_public_list_includes_it(client, auth_headers):
    create_response = await client.post(
        "/api/v1/admin/tasks",
        headers=auth_headers,
        json={
            "id": "literature-review-task",
            "name": "Literature Review",
            "description": "Summarize project literature.",
            "workflow_id": "literature_synthesizer",
            "input_schema": {"type": "object", "required": ["query"]},
            "starter_prompts": ["Summarize the main findings in this project."],
            "project_context_policy": {"source_scope": "all_project_sources"},
            "result_presentation": {"mode": "chat"},
            "is_enabled": True,
        },
    )
    assert create_response.status_code == 201

    list_response = await client.get("/api/v1/tasks", headers=auth_headers)
    assert list_response.status_code == 200
    assert {item["id"] for item in list_response.json()} == {"literature-review-task"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
backend/.venv/bin/pytest tests/test_tasks_api.py::test_admin_can_create_task_and_public_list_includes_it -v
```

Expected: FAIL because schemas/routes do not exist yet.

- [ ] **Step 3: Add the Pydantic schemas**

Create `backend/app/schemas/task.py`.

```python
from pydantic import BaseModel, Field


class TaskDefinitionBase(BaseModel):
    id: str
    version: int = 1
    name: str
    description: str
    workflow_id: str
    input_schema: dict = Field(default_factory=dict)
    starter_prompts: list[str] = Field(default_factory=list)
    project_context_policy: dict = Field(default_factory=dict)
    result_presentation: dict = Field(default_factory=dict)
    is_enabled: bool = True


class TaskDefinitionCreate(TaskDefinitionBase):
    pass


class TaskDefinition(TaskDefinitionBase):
    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Add task service helpers**

Create `backend/app/services/task_service.py` with list/get/create helpers.

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_definition import TaskDefinitionRecord


async def list_task_definitions(db: AsyncSession) -> list[TaskDefinitionRecord]:
    result = await db.execute(
        select(TaskDefinitionRecord)
        .where(TaskDefinitionRecord.is_enabled.is_(True))
        .order_by(TaskDefinitionRecord.name.asc())
    )
    return list(result.scalars().all())


async def list_all_task_definitions(db: AsyncSession) -> list[TaskDefinitionRecord]:
    result = await db.execute(
        select(TaskDefinitionRecord).order_by(TaskDefinitionRecord.name.asc())
    )
    return list(result.scalars().all())
```

- [ ] **Step 5: Add public task APIs**

Create `backend/app/api/tasks.py` with `GET /tasks` and `GET /tasks/{id}`.

- [ ] **Step 6: Add admin task create/list APIs**

Modify `backend/app/api/admin.py` to add:

```python
@router.get("/tasks", response_model=list[TaskDefinition])
@router.post("/tasks", response_model=TaskDefinition, status_code=201)
```

Validate that `workflow_id` exists before saving.

- [ ] **Step 7: Register the new router**

Update `backend/app/main.py` to include the tasks router.

- [ ] **Step 8: Run the focused tests**

Run:

```bash
backend/.venv/bin/pytest tests/test_tasks_api.py -v
```

Expected: PASS for the new task list and admin-create coverage.

---

### Task 3: Add project-level task visibility rules

**Files:**
- Modify: `backend/app/models/task_definition.py`
- Modify: `backend/app/services/task_service.py`
- Modify: `backend/app/api/tasks.py`
- Modify: `backend/app/api/sessions.py`
- Test: `tests/test_tasks_api.py`

- [ ] **Step 1: Write the failing test for project-scoped tasks**

Add a test that creates tasks, assigns them to a project, and verifies only project-allowed tasks are returned.

```python
async def test_list_tasks_can_filter_by_project(client, auth_headers):
    response = await client.get("/api/v1/tasks?project_id=project-1", headers=auth_headers)
    assert response.status_code == 200
```

Include assertions after implementation that only project-published tasks are visible.

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
backend/.venv/bin/pytest tests/test_tasks_api.py::test_list_tasks_can_filter_by_project -v
```

Expected: FAIL because project scoping is not implemented.

- [ ] **Step 3: Add a minimal project visibility field**

Extend `TaskDefinitionRecord` with a JSON field such as `project_ids`.

```python
project_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
```

Add a follow-up migration for this field if needed, or include it in the original migration if Task 1 has not been applied in development yet.

- [ ] **Step 4: Extend schemas and service filtering**

Update task schemas and task service filtering to support:

- public list of all enabled tasks when no `project_id`
- enabled tasks whose `project_ids` contains the requested project

- [ ] **Step 5: Run focused tests**

Run:

```bash
backend/.venv/bin/pytest tests/test_tasks_api.py -k project -v
```

Expected: PASS for project-scoped task visibility.

---

### Task 4: Add researcher-facing project home task launch surface

**Files:**
- Modify: `frontend/src/pages/Home.tsx`
- Create: `frontend/src/types/task.ts`
- Create: `frontend/src/components/tasks/TaskComposer.tsx`
- Create: `frontend/src/components/tasks/TaskCard.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`
- Test: `frontend` build

- [ ] **Step 1: Add the failing TypeScript surface**

Create `frontend/src/types/task.ts`.

```typescript
export interface TaskDefinition {
  id: string;
  version: number;
  name: string;
  description: string;
  workflow_id: string;
  input_schema: Record<string, unknown>;
  starter_prompts: string[];
  project_context_policy: Record<string, unknown>;
  result_presentation: Record<string, unknown>;
  is_enabled: boolean;
  project_ids?: string[];
}
```

- [ ] **Step 2: Build once to verify the task components are still missing**

Run:

```bash
npm run build
```

Expected: either PASS with no visible feature or FAIL after the next imports until the new UI is wired in.

- [ ] **Step 3: Add reusable task launch components**

Create `frontend/src/components/tasks/TaskComposer.tsx` and `TaskCard.tsx`.

`TaskComposer.tsx` responsibilities:

- large project-level input box
- controlled prompt value
- callback when user submits prompt

`TaskCard.tsx` responsibilities:

- task title
- one-line description
- CTA for launching task

- [ ] **Step 4: Load tasks into the home page**

Modify `frontend/src/pages/Home.tsx` to fetch `/tasks` and render:

- large input box near the top of the project home
- recommended task cards for the selected project

Do not remove existing project/session capabilities yet; add the new task launch band above them.

- [ ] **Step 5: Add locale strings**

Add researcher-facing strings for:

- project task prompt
- recommended tasks
- open task
- continue task

- [ ] **Step 6: Run frontend build**

Run:

```bash
npm run build
```

Expected: PASS with the project home task launcher visible.

---

### Task 5: Add chat-style task workspace page

**Files:**
- Create: `frontend/src/pages/TaskWorkspace.tsx`
- Create: `frontend/src/components/tasks/TaskSidebar.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`
- Test: `frontend` build

- [ ] **Step 1: Add a failing route reference**

Update `frontend/src/App.tsx` to add a route shape for task workspaces:

```tsx
<Route path="/projects/:projectId/tasks/:taskId" element={<TaskWorkspace />} />
```

This should initially fail until `TaskWorkspace` exists.

- [ ] **Step 2: Run build to verify the route fails**

Run:

```bash
npm run build
```

Expected: FAIL because `TaskWorkspace` is not implemented yet.

- [ ] **Step 3: Create the task workspace shell**

Create `frontend/src/pages/TaskWorkspace.tsx` with:

- task header
- main conversation area
- right-side context panel
- bottom follow-up input

Minimal starter shell:

```tsx
export default function TaskWorkspace() {
  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Content>task conversation</Content>
      <Sider width={320}>task context</Sider>
    </Layout>
  );
}
```

- [ ] **Step 4: Add the right-side context component**

Create `frontend/src/components/tasks/TaskSidebar.tsx` for:

- current project
- selected docs summary
- task parameters
- save-to-memory affordances placeholder

- [ ] **Step 5: Add locale strings and build**

Run:

```bash
npm run build
```

Expected: PASS with a reachable task workspace shell.

---

### Task 6: Connect task launch to workflow execution

**Files:**
- Modify: `frontend/src/pages/TaskWorkspace.tsx`
- Modify: `frontend/src/pages/Home.tsx`
- Modify: `frontend/src/types/workflow.ts`
- Modify: `backend/app/api/tasks.py`
- Test: `tests/test_tasks_api.py`, `tests/test_workflows_api.py`, frontend build

- [ ] **Step 1: Write the failing backend test for task launch metadata**

Add a test that reads a task and uses its `workflow_id` to start a workflow run.

```python
async def test_task_definition_exposes_workflow_id_for_launch(client, auth_headers):
    response = await client.get("/api/v1/tasks", headers=auth_headers)
    assert response.status_code == 200
    assert "workflow_id" in response.json()[0]
```

- [ ] **Step 2: Run the focused backend test**

Run:

```bash
backend/.venv/bin/pytest tests/test_tasks_api.py -k workflow_id -v
```

Expected: FAIL if the API payload does not yet include launch-ready metadata.

- [ ] **Step 3: Wire task launch from project home**

Modify `frontend/src/pages/Home.tsx` so clicking a task opens:

```text
/projects/:projectId/tasks/:taskId
```

with the initial prompt carried in router state or query params.

- [ ] **Step 4: Run workflow from the task workspace**

Modify `frontend/src/pages/TaskWorkspace.tsx` to:

- load the task definition
- create or reuse a backing session
- call `POST /workflows/{workflow_id}/run`
- render status and result summary in the task conversation stream

- [ ] **Step 5: Reuse existing workflow detail fetch**

Where possible, adapt the existing session workflow visibility logic rather than duplicating status normalization.

- [ ] **Step 6: Run focused backend tests**

Run:

```bash
backend/.venv/bin/pytest tests/test_tasks_api.py tests/test_workflows_api.py -k task -v
```

Expected: PASS for task metadata plus existing workflow execution behavior.

- [ ] **Step 7: Run frontend build**

Run:

```bash
npm run build
```

Expected: PASS with task launch connected to workflow runs.

---

### Task 7: Add admin task publishing page

**Files:**
- Create or Modify: `frontend/src/pages/admin/Tasks.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`
- Test: frontend build

- [ ] **Step 1: Add the failing route import**

Wire `/admin/tasks` into `frontend/src/App.tsx`.

- [ ] **Step 2: Run build to verify it fails without the page**

Run:

```bash
npm run build
```

Expected: FAIL if the page has not been added yet.

- [ ] **Step 3: Build the admin task page**

The admin page should support:

- listing tasks
- creating a task from a workflow
- assigning visible projects
- enabling/disabling tasks

This page should speak in task-publishing language rather than raw runtime language.

- [ ] **Step 4: Run frontend build**

Run:

```bash
npm run build
```

Expected: PASS with admin task publishing available.

---

### Task 8: Add transition language and hide runtime concepts from researcher surfaces

**Files:**
- Modify: `frontend/src/pages/Home.tsx`
- Modify: `frontend/src/pages/Session.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: locale files
- Test: frontend build and manual verification

- [ ] **Step 1: Audit visible researcher strings**

Replace or suppress researcher-facing mentions of:

- skill
- workflow catalog
- agent mode

where those concepts are not necessary for ordinary task use.

- [ ] **Step 2: Keep compatibility routes without frontstage emphasis**

Legacy session and agent pathways may remain, but remove them from the primary mental model of the researcher experience.

- [ ] **Step 3: Run frontend build**

Run:

```bash
npm run build
```

Expected: PASS with updated user-facing language.

---

### Task 9: Verification and rollout checkpoint

**Files:**
- Modify: whichever files were touched above
- Test: backend and frontend checks

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
backend/.venv/bin/pytest tests/test_tasks_api.py tests/test_workflows_api.py -v
```

Expected: PASS, except for any documented pre-existing fixture instability.

- [ ] **Step 2: Run frontend build**

Run:

```bash
npm run build
```

Expected: PASS

- [ ] **Step 3: Run manual product verification**

Verify manually:

1. admin can create a task bound to a workflow
2. admin can publish it to a project
3. researcher opens project home
4. researcher sees large prompt plus recommended tasks
5. clicking a task opens the task workspace
6. task workspace can run the linked workflow
7. results remain visible and traceable

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/task_definition.py backend/app/schemas/task.py backend/app/api/tasks.py backend/app/services/task_service.py backend/app/models/__init__.py backend/app/api/admin.py backend/app/api/sessions.py backend/app/api/workflows.py backend/app/main.py backend/alembic/versions frontend/src/types/task.ts frontend/src/pages/TaskWorkspace.tsx frontend/src/components/tasks/TaskComposer.tsx frontend/src/components/tasks/TaskCard.tsx frontend/src/components/tasks/TaskSidebar.tsx frontend/src/pages/Home.tsx frontend/src/App.tsx frontend/src/pages/admin/Tasks.tsx frontend/src/pages/admin/Workflows.tsx frontend/src/locales/en-US.json frontend/src/locales/zh-CN.json tests/test_tasks_api.py tests/test_workflows_api.py docs/superpowers/specs/2026-07-14-project-task-workbench-design.md docs/superpowers/plans/2026-07-14-project-task-workbench-implementation-plan.md
git commit -m "feat: add project task workbench foundation"
```

---

## Self-review

### Spec coverage

This plan covers:

- researcher-first project home
- large prompt plus recommended tasks
- chat-style task workspace
- task as a wrapper around workflow
- admin-only skill/workflow complexity
- project-scoped task availability

### Placeholder scan

The plan intentionally leaves the Alembic timestamp filename open, because the exact revision ID must be generated at implementation time. All other implementation areas have explicit file targets and concrete checks.

### Type consistency

The plan uses:

- `TaskDefinitionRecord` for persistence
- `TaskDefinition` / `TaskDefinitionCreate` for API
- `workflow_id` as the execution link
- `project_ids` as initial project-availability storage

These names are consistent across backend and frontend tasks.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-14-project-task-workbench-implementation-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
