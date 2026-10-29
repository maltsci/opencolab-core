# Task Result Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a task completion delivery panel that lets researchers save completed task results to research memory and export a Markdown research note.

**Architecture:** Reuse the existing task workspace, workflow run polling, latest assistant message, and `/workflow-runs/{id}/save-memory` API. Keep report export client-side for v1 by generating Markdown from the project, task, request, workflow steps, and final assistant result.

**Tech Stack:** React, TypeScript, Ant Design, existing OpenColab REST API, browser Clipboard and Blob download APIs.

---

### Task 1: Task Workspace Result Delivery

**Files:**
- Modify: `frontend/src/pages/TaskWorkspace.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`

- [ ] **Step 1: Add delivery state and helpers**

Add state for save type, save title, saving flag, saved object id, and Markdown export helpers in `TaskWorkspace.tsx`.

- [ ] **Step 2: Save completed workflow result to research memory**

When the workflow run is completed and a latest assistant result exists, call `POST /workflow-runs/{runId}/save-memory` with `{ type, title, content, relation: { enabled: false } }`, show success or error, and remember the saved object id.

- [ ] **Step 3: Generate and copy/download Markdown**

Generate Markdown with project, task, request, workflow steps, final result, and timestamp. Provide copy and `.md` download actions.

- [ ] **Step 4: Add localized UI text**

Add English and Chinese i18n keys for the result delivery panel, save controls, copy/download actions, and messages.

- [ ] **Step 5: Verify**

Run:

```bash
cd frontend
npm run build
```

Expected: TypeScript and Vite build pass.
