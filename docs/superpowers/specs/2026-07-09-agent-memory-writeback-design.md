# Agent Memory Writeback v0 Design

Date: 2026-07-09
Status: Draft

## Summary

This iteration adds the smallest useful bridge between OpenColab's research agents and its emerging research memory layer.

Today, an agent run produces:

- a structured answer
- citations
- a replayable trace

But that output still ends as a transient response unless the user manually saves it and then manually adds follow-up structure.

This design adds a minimal writeback flow:

1. A user can save an agent result as a `ResearchObject`
2. The save flow can optionally create one `ResearchObjectRelation`
3. The created relation automatically inherits the agent run trace and citations as evidence

The goal is not autonomous memory building. The goal is to let agent work become reusable scientific memory with one lightweight user action.

## Product Goal

OpenColab already has:

- document-grounded chat
- deterministic research agents
- session-scoped research objects
- relation editing with evidence

The missing link is:

> Let a useful agent output become a reusable research object and relation without forcing the user to rebuild the context by hand.

This is the first real bridge from:

`agent output`

to

`research memory`

to

`future scientific reasoning`

## Scope

### In scope

- Add a save flow for agent outputs into `ResearchObject`
- Allow the user to choose the saved object type:
  - `hypothesis`
  - `discussion`
- Allow the user to optionally create one outgoing relation from the new object to an existing object in the same session
- Reuse the existing relation model and nested evidence structure
- Auto-fill relation evidence from the agent run trace:
  - `trace_id`
  - `citations`
- Keep the workflow inside the existing Session page

### Out of scope

- Automatic relation inference with no user confirmation
- Creating multiple relations in one save action
- Background memory writeback
- Agent-authored relation creation without a UI step
- New graph visualization
- Cross-session or cross-project memory linking

## User Flow

### Primary flow

1. The user runs `Literature Synthesizer` or `Reviewer Assistant`
2. The agent response appears in the Session page as it does today
3. The user chooses a new action on that response:
   - `Save to Research Memory`
4. A lightweight modal opens
5. The user selects:
   - object type
   - title
   - optional relation target
   - optional relation type
   - optional relation note
6. The system creates the new `ResearchObject`
7. If relation fields were supplied, the system creates one relation:
   - source = newly created object
   - target = selected existing object
   - evidence = agent trace + citations + optional note
8. The new object appears in the session timeline immediately
9. If a relation was created, selecting the new object shows the relation in `Object Details`

### Secondary flow

If the user only wants to save the agent output and not connect it yet:

- the modal still creates the research object
- relation creation is skipped

This keeps the flow useful for cautious users who want to preserve the output first and structure it later.

## Session UI Design

## New action on agent messages

Agent result cards currently support actions around rerun/copy/readability. This iteration should add a memory-focused action in the same action cluster.

Recommended label:

- `Save to Research Memory`

This action should only appear on messages produced by agent runs.

It should not appear on ordinary assistant chat messages, because chat already has its own save flow.

## Save modal

The modal should be intentionally small and practical.

Fields:

- `Object Type`
  - `hypothesis`
  - `discussion`
- `Title`
  - prefilled from the agent output summary when possible
- `Content`
  - prefilled from the rendered agent output text
- `Create relation` toggle
- If enabled:
  - `Relation Type`
    - `supports`
    - `contradicts`
  - `Target Object`
    - another research object from the same session
  - `Evidence Note`
    - optional user note merged into the relation evidence payload

Default behavior:

- relation creation is off by default
- if enabled, the relation target cannot be the object being created

## Data model and persistence

This iteration should reuse the existing models.

### Research object

The saved object should keep the same shape as the existing manual save flow.

Important `content_json` fields for agent-originated objects:

- `session_id`
- `origin = "agent_run"`
- `agent_run_id`
- `trace_id`
- `source_ids`

This keeps the saved object traceable back to the run that produced it.

### Relation evidence

If a relation is created from the modal, it should use the same nested payload already established by the relation evidence refinement work:

```json
{
  "confidence": 0.8,
  "evidence": {
    "trace_id": "trace-123",
    "citations": [],
    "note": "Optional user note"
  }
}
```

Evidence fill rules:

- `confidence` defaults to `0.8` for this modal in v0
- `evidence.trace_id` comes from the agent run trace when available
- `evidence.citations` comes from the agent run trace citations when available
- `evidence.note` comes from the optional user-entered note

The key design rule is:

The relation should inherit machine evidence automatically, while still leaving space for a human rationale note.

## Backend API Design

This iteration should avoid forcing the frontend to orchestrate multiple loosely coupled requests without a shared contract.

Recommended route:

`POST /api/v1/agents/runs/{run_id}/save-memory`

Request shape:

```json
{
  "type": "hypothesis",
  "title": "Candidate controversy on antimicrobial peptide design",
  "content": "Rendered or normalized agent output text",
  "relation": {
    "enabled": true,
    "relation_type": "supports",
    "target_object_id": "object-123",
    "note": "This synthesizer output strengthens the existing hypothesis."
  }
}
```

Behavior:

1. verify the run belongs to the current user
2. verify the run belongs to the current session
3. create the new research object from the agent result
4. if relation is enabled:
   - verify target object is in the same session
   - create a relation from the new object to the target object
   - auto-populate nested evidence from the run trace
5. return the created object plus optional created relation

Response shape:

```json
{
  "research_object": {
    "id": "object-1",
    "type": "hypothesis"
  },
  "relation": {
    "id": "relation-1",
    "relation_type": "supports"
  }
}
```

## Why a dedicated API instead of two frontend calls

The save action is one conceptual user action.

Making the frontend call:

1. create object
2. fetch trace
3. create relation

would scatter the contract across three places and make the logic brittle.

A single backend route keeps:

- authorization
- trace lookup
- evidence fill
- rollback behavior

in one place.

## Error handling

The save-memory flow should fail gracefully.

Cases to handle:

- agent run not found
- target relation object not found
- target object not in same session
- duplicate relation
- object save succeeds but relation create fails

Recommended behavior:

- perform both object and optional relation creation in one transaction
- if relation creation fails, roll back the whole save-memory action
- show one user-facing error toast

This keeps the action atomic and easier to reason about.

## Frontend state behavior

After success:

- prepend the created research object to the local timeline state
- if a relation was created, cache it under the new object's `relationsByObjectId`
- optionally auto-select the created object

Recommended v0 behavior:

- auto-select the created object after save

This gives the user immediate confirmation that the agent output is now part of the research memory layer.

## Testing

### Backend

Add coverage for:

- save agent run as research object
- save agent run plus relation
- relation evidence inherits trace and citations
- invalid target object rejected
- cross-session target rejected
- missing trace still allows object save and relation save with empty evidence payload

### Frontend

At minimum verify:

- agent result shows the save-memory action
- modal submits successfully
- timeline updates after save
- nested evidence note is sent only when present
- build remains green

## Why this is the right v0

This is the smallest step that turns agents from output generators into contributors to long-term research structure.

It does not require:

- autonomous graph building
- workflow orchestration
- complex notebook abstractions

But it does create a strong foundation for the next layer:

- agent-assisted relation suggestion
- agent-authored hypothesis tracking
- long-lived scientific reasoning memory

In short:

the system stops merely answering research questions and starts preserving research conclusions in a reusable form.
