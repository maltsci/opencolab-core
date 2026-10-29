# Project Q&A Session Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Launch Project Q&A in a standard session and include searchable documents nested in project source groups in its Codex context.

**Architecture:** A project-linked source group synchronizes explicit `ProjectAssetLink` records for its leaf-document assets before the research-context service authorizes and loads chunks. Home creates a `project-qa` session and opens `/sessions/:id`; the session detects that task and calls the orchestration endpoint. The returned context manifest powers an auditable summary panel.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, React, TypeScript, Ant Design, pytest, Vite.

---

### Task 1: Synchronize project-linked source groups before context construction

**Files:**
- Modify: `backend/app/services/research_context.py:40-132`
- Modify: `tests/test_orchestration_runs.py:226-308`

- [ ] **Step 1: Write the failing group-expansion test**

Create a project-linked group with two child files and chunks. Call `build_orchestration_context` and assert the children receive project links before context construction:

```python
assert set(manifest["source_ids"]) == {child_one.id, child_two.id}
assert {chunk.source_id for chunk in context.chunks} == {child_one.id, child_two.id}
```

- [ ] **Step 2: Verify RED**

Run `backend/.venv/bin/pytest tests/test_orchestration_runs.py::test_build_orchestration_context_expands_project_source_groups -q`.

Expected: FAIL because the current context has the group ID, no child project links, and no child chunks.

- [ ] **Step 3: Expand project source groups**

Add a focused synchronization helper which resolves group leaves, materializes a source asset when needed, and calls the existing `link_asset_to_project` for each leaf. Invoke it before expanding and authorizing project source IDs. Then expand group IDs before the leaf-source authorization loop:

```python
await sync_project_group_members(db=db, project_id=project_id, user=user)
expanded_source_ids = await expand_source_ids_for_rag(project_source_ids, db)
```

- [ ] **Step 4: Verify GREEN and commit**

Run the Step 2 command; expected PASS. Then run `git add backend/app/services/research_context.py tests/test_orchestration_runs.py && git commit -m "fix: expand project source groups for qa context"`.

### Task 2: Start Project Q&A from the standard session page

**Files:**
- Modify: `frontend/src/pages/Home.tsx:510-545`
- Modify: `frontend/src/pages/Session.tsx:1033-1145`
- Modify: `frontend/src/types/orchestration.ts`

- [ ] **Step 1: Create a Project Q&A session from Home**

In `startTask`, branch on `taskId === 'project-qa'`, create the session, and navigate directly:

```tsx
const { data: session } = await apiClient.post('/sessions', {
  project_id: activeProject.id,
  task_id: taskId,
  title: task.name,
});
navigate(`/sessions/${session.id}`, { state: { draft: trimmedPrompt } });
```

Preserve the existing task-workbench route for every other task.

- [ ] **Step 2: Use orchestration for Project Q&A user turns**

When `sessionInfo.task_id === 'project-qa'`, post `{ goal: trimmedInput }` to `/sessions/${sessionId}/orchestration-runs/project-qa`, reload persisted messages after completion, and show the existing task failure translation on error. Do not call the WebSocket path for this task.

- [ ] **Step 3: Verify and commit**

Run `cd frontend && npm run build`; expected exit code 0. Then run `git add frontend/src/pages/Home.tsx frontend/src/pages/Session.tsx frontend/src/types/orchestration.ts && git commit -m "feat: launch project qa in sessions"`.

### Task 3: Show the Project Q&A context manifest in the session

**Files:**
- Modify: `backend/app/services/orchestration_service.py:79-105`
- Modify: `frontend/src/pages/Session.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`
- Modify: `tests/test_orchestration_runs.py`

- [ ] **Step 1: Write the failing manifest test**

Extend the group fixture to assert the safe manifest contains source and chunk counts but no raw chunk text:

```python
assert manifest["source_count"] == 2
assert manifest["chunk_count"] == 2
assert "document body" not in str(manifest)
```

- [ ] **Step 2: Persist safe counts**

In `build_orchestration_context`, add `source_count` and `chunk_count` beside existing `source_ids`, `chunk_ids`, and limits. Do not add chunk text.

- [ ] **Step 3: Render the context summary**

Load the latest orchestration run for a Project Q&A session and render a collapsed Ant Design panel above the composer. Show translated title, resolved source count, chunk count, and a translated empty explanation when both counts are zero.

- [ ] **Step 4: Verify and commit**

Run `backend/.venv/bin/pytest tests/test_orchestration_runs.py -q` and `cd frontend && npm run build`; expected PASS. Then run `git add backend/app/services/orchestration_service.py frontend/src/pages/Session.tsx frontend/src/locales/en-US.json frontend/src/locales/zh-CN.json tests/test_orchestration_runs.py && git commit -m "feat: show project qa context summary"`.

### Task 4: End-to-end verification

**Files:**
- Verify: `backend/app/services/research_context.py`
- Verify: `frontend/src/pages/Home.tsx`
- Verify: `frontend/src/pages/Session.tsx`

- [ ] **Step 1: Run focused backend tests**

Run `backend/.venv/bin/pytest tests/test_orchestration_runs.py tests/test_research_assets.py -q`.

Expected: PASS.

- [ ] **Step 2: Browser smoke test**

Select 医疗项目 then 项目问答 on Home. Confirm a standard `/sessions/:id` page opens without the task workbench. Confirm the context panel reports two resolved documents and searchable chunks. Send a question and confirm the completed answer appears through the Project Q&A orchestration run.
