# Session Workflow Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make workflow-backed agent execution visible inside each session answer card so researchers can see workflow status and step summaries without leaving the chat flow.

**Architecture:** Extend the existing Session page agent result card with an inline workflow section that progressively enhances from `AgentRunResponse.workflow_run_id` and workflow APIs. Keep the current structured agent answer primary, reuse legacy `agentRun.steps` as fallback, and avoid introducing a separate workflow page or debug drawer in this iteration.

**Tech Stack:** React 19, TypeScript, Ant Design, Axios, Vite, existing i18n JSON locales

---

## File Map

- Modify: `frontend/src/pages/Session.tsx`
  - Add workflow detail fetch logic keyed by `workflow_run_id`
  - Normalize workflow step display data
  - Render the inline workflow block inside existing agent answer cards
  - Add local expand/collapse behavior
- Modify: `frontend/src/types/workflow.ts`
  - Tighten workflow response typing needed by the Session page
  - Add a small normalized shape if helpful
- Modify: `frontend/src/locales/en-US.json`
  - Add workflow visibility labels
- Modify: `frontend/src/locales/zh-CN.json`
  - Add workflow visibility labels
- Verify: `frontend/package.json`
  - Reuse the existing `npm run build` verification path

## Constraints

- Do not add a new admin page in this iteration.
- Do not show raw workflow payloads, timestamps, IDs, or stack traces in the inline card.
- Do not regress current agent answer rendering when `workflow_run_id` is missing or workflow fetch fails.
- The repository currently has no frontend unit test runner configured. Verification should rely on TypeScript build, local UI smoke checks, and existing backend API compatibility.

### Task 1: Add workflow UI strings and response typing

**Files:**
- Modify: `frontend/src/types/workflow.ts`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`

- [ ] **Step 1: Update workflow response types for Session consumption**

Add or adjust types in [workflow.ts](frontend/src/types/workflow.ts) so the Session page can safely consume workflow runs and step runs:

```ts
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
  created_at?: string | null;
  updated_at?: string | null;
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

- [ ] **Step 2: Add workflow visibility locale keys**

Add minimal labels to [en-US.json](frontend/src/locales/en-US.json) and [zh-CN.json](frontend/src/locales/zh-CN.json):

```json
"workflow.sectionTitle": "Workflow",
"workflow.sectionTitleShort": "Workflow",
"workflow.statusLabel": "Status",
"workflow.stepCount": "{{count}} steps",
"workflow.showMore": "Show more",
"workflow.showLess": "Show less",
"workflow.summaryEmpty": "No step summary available",
"workflow.status.completed": "Completed",
"workflow.status.failed": "Failed",
"workflow.status.running": "Running",
"workflow.status.pending": "Pending",
"workflow.status.cancelled": "Cancelled",
"workflow.status.waiting_for_checkpoint": "Waiting",
"workflow.status.skipped": "Skipped"
```

Chinese equivalents should be natural researcher-facing text rather than debug language.

- [ ] **Step 3: Run frontend build to catch typing or JSON issues**

Run: `cd frontend && npm run build`

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/workflow.ts frontend/src/locales/en-US.json frontend/src/locales/zh-CN.json
git commit -m "feat: add workflow visibility frontend types"
```

### Task 2: Add workflow fetch and normalization to Session page

**Files:**
- Modify: `frontend/src/pages/Session.tsx`
- Read: `frontend/src/services/api-client.ts`
- Read: `frontend/src/types/agent.ts`
- Read: `frontend/src/types/workflow.ts`

- [ ] **Step 1: Add local workflow state keyed by run id**

Inside [Session.tsx](frontend/src/pages/Session.tsx), add small state containers for fetched workflow data and expanded cards:

```ts
interface WorkflowStepDisplayItem {
  key: string;
  name: string;
  status: string;
  summary: string;
}

interface WorkflowCardState {
  status: string;
  stepCount: number;
  steps: WorkflowStepDisplayItem[];
  source: 'workflow' | 'legacy';
}

const [workflowByRunId, setWorkflowByRunId] = useState<Record<string, WorkflowCardState>>({});
const [expandedWorkflowRunIds, setExpandedWorkflowRunIds] = useState<Record<string, boolean>>({});
```

- [ ] **Step 2: Add normalization helpers for workflow card display**

Add helper functions near the existing agent normalization helpers:

```ts
function normalizeWorkflowStepName(step: StepRunResponse): string {
  const outputName = typeof step.output_payload.name === 'string' ? step.output_payload.name.trim() : '';
  return outputName || step.step_id;
}

function normalizeWorkflowStepSummary(step: StepRunResponse, t: (key: string) => string): string {
  const outputSummary = typeof step.output_payload.summary === 'string' ? step.output_payload.summary.trim() : '';
  return outputSummary || t('workflow.summaryEmpty');
}

function buildLegacyWorkflowCard(run: AgentRunResponse, t: (key: string) => string): WorkflowCardState | null {
  if (!run.steps.length) return null;
  return {
    status: run.status,
    stepCount: run.steps.length,
    source: 'legacy',
    steps: run.steps.map((step, index) => ({
      key: `${run.id}-legacy-${index}`,
      name: step.name,
      status: step.status,
      summary: step.summary || t('workflow.summaryEmpty'),
    })),
  };
}
```

- [ ] **Step 3: Add workflow API loader**

Add a small loader that fetches workflow run details and steps when `workflow_run_id` exists:

```ts
async function loadWorkflowCard(runId: string, fallbackRun: AgentRunResponse, t: (key: string) => string) {
  const [runResponse, stepsResponse] = await Promise.all([
    apiClient.get<WorkflowRunResponse>(`/workflow-runs/${runId}`),
    apiClient.get<StepRunResponse[]>(`/workflow-runs/${runId}/steps`),
  ]);

  return {
    status: runResponse.data.status,
    stepCount: stepsResponse.data.length,
    source: 'workflow' as const,
    steps: stepsResponse.data.map((step) => ({
      key: step.id,
      name: normalizeWorkflowStepName(step),
      status: step.status,
      summary: normalizeWorkflowStepSummary(step, t),
    })),
  };
}
```

If the request fails, store legacy fallback instead of throwing UI-level errors.

- [ ] **Step 4: Trigger workflow fetch when messages change**

Add an effect that scans current `messages`, finds agent runs with `workflow_run_id`, and hydrates workflow cards only once per run id:

```ts
useEffect(() => {
  messages.forEach((msg) => {
    const run = msg.agentRun;
    if (!run?.workflow_run_id || workflowByRunId[run.workflow_run_id]) return;

    const fallback = buildLegacyWorkflowCard(run, t);
    if (fallback) {
      setWorkflowByRunId((prev) => ({ ...prev, [run.workflow_run_id!]: fallback }));
    }

    void loadWorkflowCard(run.workflow_run_id, run, t)
      .then((card) => {
        setWorkflowByRunId((prev) => ({ ...prev, [run.workflow_run_id!]: card }));
      })
      .catch(() => {
        // Keep legacy fallback if available; never interrupt the answer card.
      });
  });
}, [messages, t, workflowByRunId]);
```

If you need to avoid dependency churn, extract only the run ids you care about and guard updates carefully.

- [ ] **Step 5: Run frontend build**

Run: `cd frontend && npm run build`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Session.tsx
git commit -m "feat: load workflow details in session"
```

### Task 3: Render inline workflow visibility inside agent answer cards

**Files:**
- Modify: `frontend/src/pages/Session.tsx`
- Read: `frontend/src/locales/en-US.json`
- Read: `frontend/src/locales/zh-CN.json`

- [ ] **Step 1: Add a small status label formatter**

Add a helper in [Session.tsx](frontend/src/pages/Session.tsx):

```ts
function getWorkflowStatusLabel(status: string, t: (key: string) => string): string {
  return t(`workflow.status.${status}`);
}
```

If locale lookup is missing, fall back to the raw status string.

- [ ] **Step 2: Add an inline workflow renderer**

Create a renderer near the existing agent output helpers:

```tsx
function renderWorkflowBlock(
  run: AgentRunResponse,
  workflowCard: WorkflowCardState | null,
  expanded: boolean,
  onToggleExpanded: () => void,
  t: (key: string, options?: Record<string, unknown>) => string,
) {
  if (!workflowCard) return null;

  const visibleSteps = expanded ? workflowCard.steps : workflowCard.steps.slice(0, 3);
  const shouldShowToggle = workflowCard.steps.length > 3;

  return (
    <div style={{ borderTop: '1px solid #d9d9d9', paddingTop: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 8 }}>
        <div style={{ fontSize: 12, color: '#8c8c8c' }}>{t('workflow.sectionTitle')}</div>
        <Space size={8}>
          <Tag color={workflowCard.status === 'completed' ? 'green' : workflowCard.status === 'failed' ? 'red' : 'blue'}>
            {getWorkflowStatusLabel(workflowCard.status, t)}
          </Tag>
          <span style={{ fontSize: 12, color: '#8c8c8c' }}>{t('workflow.stepCount', { count: workflowCard.stepCount })}</span>
        </Space>
      </div>
      <List
        size="small"
        split={false}
        dataSource={visibleSteps}
        renderItem={(step) => (
          <List.Item style={{ padding: '6px 0', display: 'block' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
              <strong>{step.name}</strong>
              <span style={{ fontSize: 12, color: '#8c8c8c' }}>{getWorkflowStatusLabel(step.status, t)}</span>
            </div>
            <div style={{ fontSize: 12, color: '#595959', marginTop: 4 }}>{step.summary}</div>
          </List.Item>
        )}
      />
      {shouldShowToggle && (
        <Button type="link" size="small" onClick={onToggleExpanded} style={{ padding: 0, marginTop: 4 }}>
          {expanded ? t('workflow.showLess') : t('workflow.showMore')}
        </Button>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Insert workflow block into the agent answer card**

In the existing `msg.agentRun` card body, place the workflow block after structured answer sections and before the action links:

```tsx
const workflowCard = msg.agentRun.workflow_run_id
  ? workflowByRunId[msg.agentRun.workflow_run_id] || buildLegacyWorkflowCard(msg.agentRun, t)
  : null;

const isWorkflowExpanded = msg.agentRun.workflow_run_id
  ? !!expandedWorkflowRunIds[msg.agentRun.workflow_run_id]
  : false;
```

Render:

```tsx
{renderWorkflowBlock(
  msg.agentRun,
  workflowCard,
  isWorkflowExpanded,
  () => {
    const runId = msg.agentRun?.workflow_run_id;
    if (!runId) return;
    setExpandedWorkflowRunIds((prev) => ({ ...prev, [runId]: !prev[runId] }));
  },
  t,
)}
```

- [ ] **Step 4: Keep current answer and trace behavior intact**

Verify the same card still supports:

- structured agent output
- `Save to Research Memory`
- `View trace`
- note and research object actions

Do not move or remove existing actions in this iteration.

- [ ] **Step 5: Run frontend build**

Run: `cd frontend && npm run build`

Expected: PASS

- [ ] **Step 6: Manual smoke check in the browser**

Run the local app and verify:

- an existing agent result still renders
- the new workflow block appears for workflow-backed runs
- `Show more / Show less` works
- old answers without workflow data still look normal

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Session.tsx
git commit -m "feat: show workflow summaries in session"
```

### Task 4: Final verification

**Files:**
- Verify only

- [ ] **Step 1: Run frontend build**

Run: `cd frontend && npm run build`

Expected: PASS

- [ ] **Step 2: Run backend focused workflow compatibility tests**

Run: `backend/.venv/bin/python -c 'import os, pytest; code = pytest.main(["tests/test_workflow_runtime.py", "tests/test_workflows_api.py", "tests/test_agents_api.py", "-v"]); os._exit(code)'`

Expected: PASS

- [ ] **Step 3: Inspect git status**

Run: `git status --short`

Expected: only intended implementation files changed before the final commit, then clean after commit

- [ ] **Step 4: Final commit**

```bash
git add frontend/src/pages/Session.tsx frontend/src/types/workflow.ts frontend/src/locales/en-US.json frontend/src/locales/zh-CN.json
git commit -m "feat: add session workflow visibility"
```

## Self-Review

- Spec coverage:
  - Researcher-first inline workflow visibility is covered by Tasks 2 and 3.
  - Balanced summary-only detail is covered by Task 3 renderer and constraints.
  - Fallback to legacy steps is covered by Task 2 helper and fetch failure behavior.
  - No admin/dashboard work is included.
- Placeholder scan:
  - No `TBD`/`TODO` placeholders remain.
  - Commands and file paths are explicit.
- Type consistency:
  - `workflow_run_id`, `WorkflowRunResponse`, `StepRunResponse`, and `WorkflowCardState` naming are consistent across tasks.
