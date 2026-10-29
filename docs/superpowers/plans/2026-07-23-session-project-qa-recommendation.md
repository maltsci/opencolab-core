# Session Project Q&A Recommendation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show Project Q&A first in a project session's recommended task list and keep its existing in-session start flow.

**Architecture:** The session page already merges global and project-scoped task definitions into `sessionRecommendedTasks`, then renders the first four tasks. Add a small composition helper in `Session.tsx` that inserts the built-in Project Q&A definition first, deduplicates it from API results, and caps remaining recommendations at three.

**Tech Stack:** React, TypeScript, Ant Design, existing `/tasks` REST API.

---

### Task 1: Compose Project Q&A into project-session recommendations

**Files:**
- Modify: `frontend/src/pages/Session.tsx:977-1016`
- Test: production frontend build

- [ ] **Step 1: Add a local recommendation composition helper near the existing task utilities**

```ts
const PROJECT_QA_TASK_ID = 'project-qa';

const composeSessionRecommendedTasks = (tasks: TaskDefinition[]) => {
  const projectQa = tasks.find((task) => task.id === PROJECT_QA_TASK_ID);
  if (!projectQa) return tasks;
  return [
    projectQa,
    ...tasks.filter((task) => task.id !== PROJECT_QA_TASK_ID),
  ];
};
```

- [ ] **Step 2: Apply the helper after both successful and fallback task loads**

```ts
const merged = new Map<string, TaskDefinition>();
[...globalTasks, ...projectResponse.data].forEach((task) => merged.set(task.id, task));
setSessionRecommendedTasks(composeSessionRecommendedTasks(Array.from(merged.values())));
```

```ts
setSessionRecommendedTasks(composeSessionRecommendedTasks(globalTasks));
```

- [ ] **Step 3: Verify the existing four-card limit retains Project Q&A plus at most three others**

The existing render remains:

```tsx
{sessionRecommendedTasks.slice(0, 4).map((task) => (
```

- [ ] **Step 4: Run the production frontend build**

Run: `docker compose exec -T frontend npm run build`

Expected: Vite production build completes successfully. A bundle-size warning is acceptable.

- [ ] **Step 5: Commit the implementation**

```bash
git add frontend/src/pages/Session.tsx
git commit -m "feat: recommend project qa in sessions"
```
