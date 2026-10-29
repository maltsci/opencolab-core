# Orchestrator Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add durable task-session identity, orchestration run persistence, filtered context snapshots, and authenticated run lifecycle APIs without changing the existing Workflow runtime path.

**Architecture:** Extend `Session` to bind a conversation to a task and retain a compact summary. Introduce a separate `OrchestrationRun` state machine instead of overloading `WorkflowRun`; its immutable policy and context snapshots make each Codex turn auditable and resumable. Existing sessions and workflows remain compatible because new fields are nullable and existing routes are unchanged.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Alembic, Pydantic v2, pytest/pytest-asyncio.

---

## File Structure

- Modify: `backend/app/models/session.py` — add task and summary fields.
- Create: `backend/app/models/orchestration_run.py` — persistent `OrchestrationRun` model.
- Modify: `backend/app/models/__init__.py` — import the new model for metadata registration.
- Create: `backend/alembic/versions/p7q8r9s0t1u2_add_orchestration_runs.py` — schema migration.
- Create: `backend/app/schemas/orchestration.py` — request/response and event-safe contracts.
- Create: `backend/app/services/orchestration_service.py` — run creation, transition validation, context snapshot, and authorization helpers.
- Create: `backend/app/api/orchestration.py` — session-scoped run APIs.
- Modify: `backend/app/main.py` and `backend/app/api/__init__.py` — register the router.
- Modify: `backend/app/schemas/session.py` and `backend/app/api/sessions.py` — accept/return `task_id` without breaking non-task sessions.
- Test: `tests/test_orchestration_runs.py`.

### Task 1: Add a failing task-session API test

**Files:**
- Create: `tests/test_orchestration_runs.py`

- [ ] **Step 1: Write the failing test for task session persistence**

```python
async def test_create_task_session_persists_task_id(client, auth_headers, project):
    response = await client.post(
        "/api/v1/sessions",
        headers=auth_headers,
        json={"project_id": project.id, "task_id": "project-qa", "title": "Q&A"},
    )

    assert response.status_code == 201
    assert response.json()["task_id"] == "project-qa"
    assert response.json()["conversation_summary"] is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_orchestration_runs.py::test_create_task_session_persists_task_id -v`

Expected: FAIL because session schemas do not expose `task_id`.

- [ ] **Step 3: Extend the session model and schemas**

Add nullable fields to `Session`:

```python
task_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
conversation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Add the same optional fields to the session create and response schemas. In the create route, pass `task_id=body.task_id` when constructing `Session`; do not require it for existing callers.

- [ ] **Step 4: Add the migration**

Create `p7q8r9s0t1u2_add_orchestration_runs.py` with:

```python
def upgrade() -> None:
    op.add_column("sessions", sa.Column("task_id", sa.String(length=100), nullable=True))
    op.add_column("sessions", sa.Column("conversation_summary", sa.Text(), nullable=True))
    op.create_index("ix_sessions_task_id", "sessions", ["task_id"], unique=False)

def downgrade() -> None:
    op.drop_index("ix_sessions_task_id", table_name="sessions")
    op.drop_column("sessions", "conversation_summary")
    op.drop_column("sessions", "task_id")
```

- [ ] **Step 5: Run the focused test**

Run: `pytest tests/test_orchestration_runs.py::test_create_task_session_persists_task_id -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/session.py backend/app/schemas/session.py backend/app/api/sessions.py backend/alembic/versions/p7q8r9s0t1u2_add_orchestration_runs.py tests/test_orchestration_runs.py
git commit -m "feat: persist task session identity"
```

### Task 2: Add the orchestration-run persistence model and contracts

**Files:**
- Create: `backend/app/models/orchestration_run.py`
- Create: `backend/app/schemas/orchestration.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/alembic/versions/p7q8r9s0t1u2_add_orchestration_runs.py`
- Modify: `tests/test_orchestration_runs.py`

- [ ] **Step 1: Write failing lifecycle tests**

```python
async def test_orchestration_run_snapshot_is_immutable(db, session, user):
    run = OrchestrationRun(
        session_id=session.id,
        task_id="project-qa",
        turn_index=1,
        status="planning",
        capability_snapshot={"skills": ["rag-retrieve"]},
        context_manifest={"chunk_ids": ["chunk-1"]},
        output_contract_snapshot={"artifact_type": "answer"},
        created_by=user.id,
    )
    db.add(run)
    await db.commit()

    assert run.status == "planning"
    assert run.capability_snapshot["skills"] == ["rag-retrieve"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_orchestration_runs.py::test_orchestration_run_snapshot_is_immutable -v`

Expected: FAIL because the model does not exist.

- [ ] **Step 3: Implement model and Pydantic contracts**

Define `OrchestrationRun` with `session_id`, `task_id`, `turn_index`, `status`, `goal_message_id`, JSON `plan_snapshot`, `capability_snapshot`, `context_manifest`, `output_contract_snapshot`, JSON `budget_usage`, nullable `sandbox_session_id`, `resume_token`, `final_message_id`, `error_code`, `error_message`, creator fields, and timestamps. Use this exact status literal in `schemas/orchestration.py`:

```python
OrchestrationRunStatus = Literal[
    "planning", "running", "waiting_for_approval", "completed", "failed", "cancelled"
]
```

Expose `OrchestrationRunCreateRequest(goal: str)` and `OrchestrationRunResponse` with snapshots and safe errors, but never expose `resume_token`.

- [ ] **Step 4: Extend the migration and metadata registration**

Add an `orchestration_runs` table with indexes on `session_id`, `task_id`, `status`, and `created_by`; add a unique constraint on `(session_id, turn_index)`. Import the model from `backend/app/models/__init__.py`.

- [ ] **Step 5: Run model tests**

Run: `pytest tests/test_orchestration_runs.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/orchestration_run.py backend/app/models/__init__.py backend/app/schemas/orchestration.py backend/alembic/versions/p7q8r9s0t1u2_add_orchestration_runs.py tests/test_orchestration_runs.py
git commit -m "feat: add orchestration run model"
```

### Task 3: Create context snapshots and the run lifecycle service

**Files:**
- Create: `backend/app/services/orchestration_service.py`
- Modify: `backend/app/services/research_context.py`
- Modify: `tests/test_orchestration_runs.py`

- [ ] **Step 1: Write failing tests for project-scoped snapshots and valid transitions**

```python
async def test_create_orchestration_run_collects_only_authorized_context(db, session, user, source):
    run = await create_orchestration_run(
        session=session,
        user=user,
        task=task_definition,
        goal_message=message,
        db=db,
    )

    assert run.context_manifest["source_ids"] == [source.id]
    assert "raw_pdf_path" not in run.context_manifest

def test_transition_rejects_completed_run():
    with pytest.raises(InvalidOrchestrationTransitionError):
        validate_orchestration_transition("completed", "running")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_orchestration_runs.py -k "context or transition" -v`

Expected: FAIL because the service functions do not exist.

- [ ] **Step 3: Implement explicit helpers**

Implement `create_orchestration_run`, `build_orchestration_context`, and `transition_orchestration_run` in `orchestration_service.py`. Reuse `collect_project_source_ids` and `build_research_execution_context`; return a manifest containing only source IDs, chunk IDs, memory IDs, artifact IDs, and configured limits. Store source text only in the transient context bundle sent to the local Sandbox, never in the manifest. Permit only:

```python
ALLOWED_TRANSITIONS = {
    "planning": {"running", "failed", "cancelled"},
    "running": {"waiting_for_approval", "completed", "failed", "cancelled"},
    "waiting_for_approval": {"running", "cancelled", "failed"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}
```

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_orchestration_runs.py -k "context or transition" -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/orchestration_service.py backend/app/services/research_context.py tests/test_orchestration_runs.py
git commit -m "feat: add orchestration lifecycle service"
```

### Task 4: Expose authenticated run lifecycle APIs

**Files:**
- Create: `backend/app/api/orchestration.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/__init__.py`
- Modify: `tests/test_orchestration_runs.py`

- [ ] **Step 1: Write failing API tests**

```python
async def test_create_and_list_orchestration_runs(client, auth_headers, task_session):
    created = await client.post(
        f"/api/v1/sessions/{task_session.id}/orchestration-runs",
        headers=auth_headers,
        json={"goal": "Summarize the project evidence."},
    )
    assert created.status_code == 201
    assert created.json()["status"] == "planning"

    listed = await client.get(
        f"/api/v1/sessions/{task_session.id}/orchestration-runs", headers=auth_headers
    )
    assert [item["id"] for item in listed.json()] == [created.json()["id"]]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_orchestration_runs.py::test_create_and_list_orchestration_runs -v`

Expected: FAIL with 404.

- [ ] **Step 3: Implement routes**

Add these routes to `orchestration.py` and use `_get_session_for_user` for project authorization:

```text
POST /sessions/{session_id}/orchestration-runs
GET  /sessions/{session_id}/orchestration-runs
GET  /orchestration-runs/{run_id}
POST /orchestration-runs/{run_id}/cancel
```

The create route must require `session.task_id`, validate the enabled task with `get_task_definition(..., project_id=session.project_id)`, persist a user `Message`, and call `create_orchestration_run`. Cancellation may transition only `planning`, `running`, and `waiting_for_approval` runs.

- [ ] **Step 4: Run API tests**

Run: `pytest tests/test_orchestration_runs.py -v`

Expected: PASS.

- [ ] **Step 5: Run regression tests**

Run: `pytest tests/test_sessions.py tests/test_tasks_api.py tests/test_workflows_api.py -v`

Expected: PASS; existing workflow routes remain unchanged.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/orchestration.py backend/app/api/__init__.py backend/app/main.py tests/test_orchestration_runs.py
git commit -m "feat: add orchestration run APIs"
```
