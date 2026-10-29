# Session Task Prompt Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the composer content with the selected task's starter prompt whenever a user switches recommended tasks.

**Architecture:** `startTaskFromCurrentSession` already owns task selection and starter-prompt initialization. Change it to assign `task.starter_prompts[0] ?? ''` unconditionally after selecting the task, leaving task execution untouched.

**Tech Stack:** React, TypeScript, Ant Design.

---

### Task 1: Synchronize the composer prompt with recommended task selection

**Files:**
- Modify: `frontend/src/pages/Session.tsx:1153-1171`
- Test: production frontend build

- [ ] **Step 1: Replace conditional starter-prompt initialization**

Replace:

```ts
setSelectedSessionTask(task);
if (!input.trim() && task.starter_prompts.length > 0) {
  setInput(task.starter_prompts[0]);
}
```

With:

```ts
setSelectedSessionTask(task);
setInput(task.starter_prompts[0] ?? '');
```

- [ ] **Step 2: Run the production frontend build**

Run: `docker compose exec -T frontend npm run build`

Expected: the build completes successfully; the existing chunk-size warning is acceptable.

- [ ] **Step 3: Commit the implementation**

```bash
git add frontend/src/pages/Session.tsx
git commit -m "feat: sync session task prompts"
```
