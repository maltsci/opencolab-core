# Orchestrator Task Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add versioned task artifacts and evolve the existing TaskWorkspace into a progressive-visibility interface for Codex orchestration, approvals, run history, and the three MVP output contracts.

**Architecture:** Keep the current project/task route and task conversation. Replace only the task-workspace execution client from `WorkflowRun` polling to `OrchestrationRun` events, while preserving the fixed-workflow fallback. Persist answers, reports, and documents as draft artifacts with immutable revisions; publishing remains an explicit approved action.

**Tech Stack:** React, TypeScript, Ant Design, React Query/API client, FastAPI, SQLAlchemy, Alembic, pytest, Vitest if configured.

---

## File Structure

- Create: `backend/app/models/task_artifact.py`, `backend/app/schemas/task_artifact.py`, `backend/app/services/task_artifact_service.py`, `backend/app/api/task_artifacts.py`.
- Create: `backend/alembic/versions/r9s0t1u2v3w4_add_task_artifacts.py`.
- Modify: `backend/app/models/__init__.py`, `backend/app/main.py`, and `backend/app/api/__init__.py`.
- Create: `frontend/src/types/orchestration.ts` and `frontend/src/types/task-artifact.ts`.
- Create: `frontend/src/components/tasks/OrchestrationPlanCard.tsx`, `RunStatusPanel.tsx`, `ApprovalCard.tsx`, and `TaskArtifactPanel.tsx`.
- Modify: `frontend/src/pages/TaskWorkspace.tsx`, `frontend/src/locales/en-US.json`, and `frontend/src/locales/zh-CN.json`.
- Test: `tests/test_task_artifacts.py`, `tests/test_orchestration_runs.py`, and frontend build.

### Task 1: Add task-artifact persistence and revision APIs

**Files:**
- Create: `backend/app/models/task_artifact.py`
- Create: `backend/app/schemas/task_artifact.py`
- Create: `backend/app/services/task_artifact_service.py`
- Create: `backend/app/api/task_artifacts.py`
- Create: `backend/alembic/versions/r9s0t1u2v3w4_add_task_artifacts.py`
- Create: `tests/test_task_artifacts.py`

- [ ] **Step 1: Write failing revision tests**

```python
async def test_create_artifact_revision_is_immutable(client, auth_headers, task_session):
    created = await client.post(
        f"/api/v1/sessions/{task_session.id}/task-artifacts",
        headers=auth_headers,
        json={"type": "document", "title": "Draft", "content_format": "markdown", "content": "# First"},
    )
    revised = await client.post(
        f"/api/v1/task-artifacts/{created.json()['id']}/revisions",
        headers=auth_headers,
        json={"content_format": "markdown", "content": "# Second"},
    )
    assert revised.json()["revision_number"] == 2
    assert created.json()["current_revision"]["content"] == "# First"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_task_artifacts.py::test_create_artifact_revision_is_immutable -v`

Expected: FAIL with 404.

- [ ] **Step 3: Implement models, service, and routes**

Use `TaskArtifact` (`session_id`, `project_id`, `task_id`, `type`, `title`, `status`, `current_revision_id`, creator, timestamps) and `TaskArtifactRevision` (`artifact_id`, `revision_number`, `content_format`, `content`, `citations_json`, `provenance_json`, `orchestration_run_id`, timestamps). Enforce a unique `(artifact_id, revision_number)` constraint. Add:

```text
POST /sessions/{session_id}/task-artifacts
GET  /sessions/{session_id}/task-artifacts
GET  /task-artifacts/{artifact_id}
POST /task-artifacts/{artifact_id}/revisions
POST /task-artifacts/{artifact_id}/publish
```

Only draft artifacts may receive revisions. The publish endpoint must create a pending approval when called outside a resolved approval flow; it must not write to the project library or research memory directly.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_task_artifacts.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/task_artifact.py backend/app/schemas/task_artifact.py backend/app/services/task_artifact_service.py backend/app/api/task_artifacts.py backend/alembic/versions/r9s0t1u2v3w4_add_task_artifacts.py tests/test_task_artifacts.py
git commit -m "feat: add versioned task artifacts"
```

### Task 2: Persist final Codex output into messages and draft artifacts

**Files:**
- Modify: `backend/app/services/orchestration_service.py`
- Modify: `backend/app/services/codex_runtime.py`
- Modify: `backend/app/api/orchestration.py`
- Modify: `tests/test_orchestration_runs.py`

- [ ] **Step 1: Write failing finalization tests**

```python
async def test_finalize_report_creates_message_and_draft_artifact(db, run):
    result = await finalize_orchestration_run(
        run=run,
        final_content="Evidence summary",
        artifact_payload={"type": "report", "title": "Synthesis", "content": "# Synthesis", "citations": []},
        db=db,
    )
    assert result.run.status == "completed"
    assert result.artifact.status == "draft"
    assert result.message.role == "assistant"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_orchestration_runs.py::test_finalize_report_creates_message_and_draft_artifact -v`

Expected: FAIL because finalization only stores workflow messages.

- [ ] **Step 3: Implement output-contract validation and finalization**

Implement `validate_orchestration_output` and `finalize_orchestration_run`. Enforce `artifact_type`, `content_format`, required sections, and citations before marking a run complete. Always create an assistant `Message`; create an artifact/revision when the output contract requests an artifact. If validation fails, keep the run failed or draft-only with a safe error and never publish it.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_orchestration_runs.py -k "finalize or output_contract" -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/orchestration_service.py backend/app/services/codex_runtime.py backend/app/api/orchestration.py tests/test_orchestration_runs.py
git commit -m "feat: finalize orchestrator artifacts"
```

### Task 3: Add frontend contracts and focused task-workspace components

**Files:**
- Create: `frontend/src/types/orchestration.ts`
- Create: `frontend/src/types/task-artifact.ts`
- Create: `frontend/src/components/tasks/OrchestrationPlanCard.tsx`
- Create: `frontend/src/components/tasks/RunStatusPanel.tsx`
- Create: `frontend/src/components/tasks/ApprovalCard.tsx`
- Create: `frontend/src/components/tasks/TaskArtifactPanel.tsx`

- [ ] **Step 1: Define API types**

```ts
export type OrchestrationRunStatus = 'planning' | 'running' | 'waiting_for_approval' | 'completed' | 'failed' | 'cancelled';

export interface OrchestrationRun {
  id: string;
  session_id: string;
  task_id: string;
  status: OrchestrationRunStatus;
  plan_snapshot: { steps?: Array<{ id: string; summary: string; status?: string }> };
  budget_usage: Record<string, number>;
  error_message?: string | null;
}
```

Define artifact and invocation interfaces with only fields returned by the API; do not duplicate backend-only tokens or encrypted data.

- [ ] **Step 2: Implement presentational components**

`OrchestrationPlanCard` accepts plan steps and renders a collapsed Ant Design `Collapse` for simple runs. `RunStatusPanel` renders status, call count, elapsed time, and budget. `ApprovalCard` accepts invocation ID plus approve/decline callbacks and disables both buttons while submitting. `TaskArtifactPanel` renders revision metadata, Markdown content, citation state, and actions for opening, revising, and publish request.

- [ ] **Step 3: Add i18n keys**

Add matching `task.orchestration.*` and `task.artifact.*` keys in both locale files. Use keys for every new visible label, error, status, and approval action; do not hardcode user-facing strings.

- [ ] **Step 4: Run the frontend build**

Run: `cd frontend && npm run build`

Expected: PASS with no TypeScript errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/orchestration.ts frontend/src/types/task-artifact.ts frontend/src/components/tasks/OrchestrationPlanCard.tsx frontend/src/components/tasks/RunStatusPanel.tsx frontend/src/components/tasks/ApprovalCard.tsx frontend/src/components/tasks/TaskArtifactPanel.tsx frontend/src/locales/en-US.json frontend/src/locales/zh-CN.json
git commit -m "feat: add orchestrator workspace components"
```

### Task 4: Integrate progressive orchestration into TaskWorkspace

**Files:**
- Modify: `frontend/src/pages/TaskWorkspace.tsx`
- Modify: `frontend/src/types/task.ts`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`

- [ ] **Step 1: Replace only the Codex task launch path**

In `ensureSession`, include `task_id: task.id` when creating a new session. In `handleStartTask`, branch by `task.orchestration_policy?.runtime`:

```ts
if (task.orchestration_policy?.runtime === 'codex') {
  const { data } = await apiClient.post<OrchestrationRun>(
    `/sessions/${activeSession.id}/orchestration-runs`,
    { goal: trimmedRequest },
  );
  setOrchestrationRun(data);
  return;
}

await apiClient.post(`/workflows/${task.workflow_id}/run`, payload);
```

Do not remove the existing fixed-workflow branch.

- [ ] **Step 2: Subscribe to orchestration events**

Use `EventSource` for `GET /orchestration-runs/{run.id}/events`. Merge `plan_created`, `tool_completed`, `approval_required`, `artifact_revision_created`, `finalized`, and `failed` events into component state. Close the source on terminal statuses and component unmount. Keep the existing workflow polling effect only for non-Codex tasks.

- [ ] **Step 3: Integrate components and approval action**

Render the plan card only when a plan exists, the status panel while a Codex run is active, and the approval card only for pending invocations. Submit approval with:

```ts
await apiClient.post(
  `/orchestration-runs/${run.id}/tool-invocations/${invocation.id}/approval`,
  { approved },
);
```

Refresh messages and artifacts after a terminal event. Display the active artifact panel below the assistant result and retain existing memory-save/download controls for fixed-workflow results.

- [ ] **Step 4: Run build and regression checks**

Run: `cd frontend && npm run build`

Expected: PASS.

Run: `pytest tests/test_orchestration_runs.py tests/test_task_artifacts.py tests/test_workflows_api.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/TaskWorkspace.tsx frontend/src/types/task.ts frontend/src/locales/en-US.json frontend/src/locales/zh-CN.json
git commit -m "feat: integrate codex task orchestration"
```

### Task 5: Verify MVP task contracts and privacy regressions

**Files:**
- Modify: `tests/test_orchestration_runs.py`
- Modify: `tests/test_tool_gateway.py`
- Modify: `tests/test_task_artifacts.py`
- Modify: `tests/test_workflows_api.py`

- [ ] **Step 1: Add end-to-end contract tests**

```python
@pytest.mark.parametrize(
    ("task_id", "artifact_type"),
    [
        ("project-qa", "answer"),
        ("literature-synthesis", "report"),
        ("research-document-draft", "document"),
    ],
)
async def test_mvp_task_contract_creates_expected_draft_artifact(client, auth_headers, task_session, task_id, artifact_type):
    task_session.task_id = task_id
    run = await create_completed_orchestration_run(client, auth_headers, task_session.id)
    artifact = await get_latest_task_artifact(client, auth_headers, task_session.id)
    assert artifact["type"] == artifact_type
    assert artifact["status"] == "draft"
```

Also assert that context manifests and ToolInvocation payloads contain no `raw_pdf_path`, `api_key`, `authorization`, `password`, or `secret` keys.

- [ ] **Step 2: Run focused acceptance tests**

Run: `pytest tests/test_orchestration_runs.py tests/test_tool_gateway.py tests/test_task_artifacts.py -v`

Expected: PASS.

- [ ] **Step 3: Run full backend and frontend verification**

Run: `pytest -v`

Expected: PASS.

Run: `cd frontend && npm run build`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_orchestration_runs.py tests/test_tool_gateway.py tests/test_task_artifacts.py tests/test_workflows_api.py
git commit -m "test: cover orchestrator task contracts"
```
