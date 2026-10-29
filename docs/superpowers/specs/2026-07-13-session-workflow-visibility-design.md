# Session Workflow Visibility Design

## Goal

Make the new workflow runtime visible to researchers inside the existing session page without turning the chat experience into an admin or debugging surface.

This iteration should answer a simple user question in-context:

`What happened when this agent answer was produced?`

## Product Intent

The previous runtime iteration made `WorkflowRun` and `StepRun` persist behind the scenes, but the session UI still feels unchanged. That is good for compatibility, but not enough for perceived product value.

This design adds a lightweight workflow presentation directly inside each agent answer card so researchers can see that:

- the answer came from a workflow-backed execution path
- the workflow completed, failed, or is still running
- the workflow had a small number of meaningful steps
- each step produced a concise summary of what happened

The design should preserve the current reading flow. The main answer remains primary. Workflow visibility becomes a secondary explanatory layer.

## Primary User

Researcher in the session page.

The target user is not trying to inspect raw payloads, timestamps, or internal runtime mechanics. They want confidence and process visibility while staying in the answer flow.

## Chosen Direction

Use an inline workflow block inside each agent answer card.

The user explicitly chose:

- researcher-first
- inline visibility instead of a separate drawer-first flow
- a balanced detail level with summaries, not a debugger view

## UX Summary

Each assistant message with an `agentRun` gains an embedded `Workflow` section below the structured agent result.

The section contains:

1. A compact workflow status row
2. A lightweight list of workflow steps
3. Short per-step summaries
4. A small expand/collapse affordance if the workflow block becomes visually large

The existing `View trace` action remains available and separate.

## Session Card Behavior

### Default State

Inside an agent answer card, show:

- existing agent result tags and structured answer content
- a new workflow block below the answer content

The workflow block shows:

- workflow label
- current workflow status
- total step count
- step rows with:
  - step display name
  - status
  - one-line summary

### Balanced Density Rules

The workflow block should feel readable, not diagnostic.

Rules:

- Do not show raw `input_payload`
- Do not show raw `output_payload`
- Do not show timestamps in v1
- Do not show internal IDs in the main card
- Do not show stack traces or full error bodies

If a step summary is long:

- clamp it to one or two lines in the collapsed state
- allow a card-level `Show more` expansion for the workflow block

### Failed Workflows

If the workflow status is `failed`:

- show failed status prominently
- show each step status
- show a short error line only when a step has a readable error summary

Still avoid raw debugging detail in the inline card.

### Missing Workflow Detail Fallback

If `workflow_run_id` exists but workflow step fetch fails:

- keep the agent answer card fully usable
- show a compact fallback workflow block using existing legacy `agentRun.steps`
- never block the answer content on workflow detail loading

If no `workflow_run_id` exists:

- keep current card behavior unchanged

## Data Strategy

The UI should support progressive enhancement.

### Primary Data Source

When `agentRun.workflow_run_id` exists, fetch:

- `GET /api/v1/workflow-runs/{id}`
- `GET /api/v1/workflow-runs/{id}/steps`

Use these to render:

- workflow status
- step list
- step summaries from `output_payload`

### Fallback Data Source

If workflow data is unavailable, fall back to existing `agentRun.steps`.

This ensures the visible workflow feature does not regress the session experience when:

- the workflow API request fails
- old agent runs do not have a linked workflow
- a partial migration state exists in local environments

## Step Display Mapping

The UI should normalize workflow steps for display into a small view model:

- `name`
- `status`
- `summary`

Mapping rules:

- prefer `output_payload.name`
- otherwise use `step_id`
- prefer `output_payload.summary`
- otherwise use an empty summary
- prefer workflow API step status when available
- otherwise use legacy `agentRun.steps[].status`

No raw workflow fields should be shown directly to the user.

## Interaction Design

### Inline Expand/Collapse

The workflow block supports two presentation states:

- collapsed
- expanded

Collapsed:

- status row always visible
- step list visible
- summaries clamped

Expanded:

- all step summaries fully readable
- no extra debug fields yet

This is a card-local interaction, not a page-wide drawer.

### Relationship to Trace View

Keep `View trace` as a separate action.

Meaning split:

- `Workflow` explains the process
- `Trace` explains the evidence basis

This avoids conflating execution steps with source evidence.

## Scope

### In Scope

- Session page inline workflow visibility for agent answers
- Researcher-first workflow summaries
- Workflow status and step summary presentation
- Graceful fallback to legacy agent step data
- Minimal i18n additions

### Out of Scope

- Admin workflow run dashboard
- Workflow creation or editing UI
- Full step payload inspection
- Timestamps and execution duration in the card
- Separate workflow details page
- Workflow-native save-to-memory UI changes

## Implementation Outline

### Frontend Files

- `frontend/src/pages/Session.tsx`
- `frontend/src/types/workflow.ts`
- `frontend/src/locales/en-US.json`
- `frontend/src/locales/zh-CN.json`

### Likely Additions

In the session page:

- local workflow detail state keyed by `workflow_run_id`
- small loader function for workflow steps
- display normalizer for workflow step cards
- inline UI block for workflow status and steps
- card-local expand/collapse state

In workflow types:

- ensure the frontend has the response shapes needed for workflow run and step data

In locales:

- add labels for workflow section title
- add status labels and expand/collapse text if needed

## Error Handling

If workflow fetch fails:

- do not toast a blocking error
- do not hide the main answer
- render fallback steps if available
- otherwise omit the workflow block quietly

This feature should improve visibility, not add fragility to the chat view.

## Testing

### Frontend Behavior

Cover at least:

- agent answer with `workflow_run_id` renders workflow section
- fetched workflow steps render normalized names, statuses, and summaries
- fallback to legacy `agentRun.steps` works when workflow fetch fails
- no workflow section is shown for old agent answers without `workflow_run_id`

### Build Verification

- frontend build passes

## Success Criteria

This iteration is successful if a researcher can run an agent in the session page and immediately observe:

- that a workflow executed
- whether it completed or failed
- what the main steps were
- what each step roughly did

without leaving the answer card or needing admin tooling.
