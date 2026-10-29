# Session Timeline and Research Objects v0 Design

Date: 2026-07-08
Status: Draft approved for review

## Summary

This design extends OpenColab's existing session workspace with two tightly scoped v0 features:

1. A lightweight notebook-style timeline embedded in the session view
2. User-created research objects for `hypothesis` and `discussion`

The goal is not to introduce a separate notebook product, graph editor, or automatic knowledge extraction system. The goal is to let a researcher turn useful answers into reusable research artifacts inside the same session where the work happened.

This iteration should complete the missing practical loop:

```text
Upload sources
  -> Ask question
  -> Get answer with citations
  -> Run research agent if needed
  -> Save a useful answer as hypothesis/discussion
  -> See saved artifacts in the session timeline
  -> Reuse them in the next research step
```

## Product Goal

The current product already supports:

- source upload and session linking
- chat with citations and trace
- research agents with structured output

What it still lacks is a visible layer for durable research artifacts. Answers disappear into the transcript unless the user manually interprets and remembers them.

The product goal of this iteration is:

> Let users promote important session outputs into durable research artifacts and view them in a simple timeline without leaving the current session.

For v0, the timeline should feel like a research thread companion, not a full notebook editor.

## Scope

This iteration must add:

1. A session-level timeline panel in the current session page
2. Manual creation of `hypothesis` and `discussion` research objects from assistant outputs
3. Backend APIs to create and list research objects scoped to a session
4. Storage of source message metadata so saved objects can point back to where they came from

This iteration will not add:

- a dedicated notebook page
- automatic hypothesis generation
- experiment objects
- visual relation graph editing
- relation authoring UI
- background inference that creates research objects automatically

## User Experience

### Session Timeline

The timeline will live inside the existing session page as a collapsible panel. It should stay subordinate to the main chat workspace.

Recommended placement:

- right-side panel area, below or alongside the existing trace/citation context
- collapsible to avoid crowding the primary Q&A flow

Timeline items for v0:

- user messages
- assistant answers
- agent results
- saved `hypothesis` objects
- saved `discussion` objects

The timeline is chronological and session-local.

### Saving Research Objects

Each assistant answer and each agent result should expose two new actions:

- `Save as Hypothesis`
- `Save as Discussion`

Clicking either action opens a small modal with:

- type (preselected and locked from the clicked action)
- title
- content preview or editable content

Default behavior:

- title is auto-derived from the first sentence or first line
- content defaults to the visible answer text
- content_json stores structured metadata when available

After saving:

- the new research object appears in the timeline
- the user gets a success toast
- the original answer remains unchanged

## Chosen Technical Route

### Why timeline in-session instead of a separate notebook page

The existing product flow is already centered on sessions. Users are actively reading answers and deciding whether an output is reusable while they are inside the session.

Adding a new page would increase navigation cost and require more scaffolding:

- routing
- empty-state design
- cross-page synchronization
- duplicate session context fetching

For v0, a session-local panel is enough to prove the notebook direction without fracturing the workflow.

### Why manual creation instead of automatic extraction

Automatic object generation sounds attractive but introduces noise:

- many answers are disposable
- not every answer deserves artifact status
- automatic `hypothesis` creation can quickly become clutter

Manual promotion keeps quality high and makes the user explicitly decide what is worth keeping.

## Data Model

The repository already contains `ResearchObject` and `ResearchObjectRelation` models. This iteration should reuse them rather than redesign them.

### ResearchObject usage for this iteration

Allowed object types in the UI:

- `hypothesis`
- `discussion`

Stored fields:

- `id`
- `type`
- `title`
- `content`
- `content_json`
- `created_by`
- `created_at`
- `updated_at`

### Additional metadata needed for v0 session use

To support timeline rendering and traceability, `content_json` should include a small source metadata envelope:

```json
{
  "session_id": "session-uuid",
  "source_message_id": "message-uuid",
  "origin": "assistant_message",
  "agent_run_id": "optional-agent-run-uuid",
  "trace_id": "optional-trace-uuid",
  "source_ids": ["source-1", "source-2"]
}
```

Rules:

- `session_id` is required for all objects created from the session UI
- `source_message_id` is required when created from a specific answer
- `agent_run_id` is optional and used when the source was an agent result
- `trace_id` is optional but should be stored when available

This keeps the schema small while making the artifact auditable.

## API Design

### Create research object

`POST /api/v1/research-objects`

Request:

```json
{
  "session_id": "session-uuid",
  "type": "hypothesis",
  "title": "Potential hypothesis title",
  "content": "User-approved hypothesis text",
  "content_json": {
    "session_id": "session-uuid",
    "source_message_id": "message-uuid",
    "origin": "assistant_message",
    "trace_id": "trace-uuid"
  }
}
```

Behavior:

- validate session access through the current user workspace
- validate type is one of `hypothesis` or `discussion`
- persist object with `created_by`
- return created object

### List research objects for a session

`GET /api/v1/sessions/{session_id}/research-objects`

Behavior:

- validate session access
- return session-scoped research objects sorted by `created_at`
- scope is determined by `content_json.session_id`

This is sufficient for the timeline panel in v0.

## Frontend Design

### Session page updates

The current session page already includes:

- source list
- transcript area
- trace/citation side panel

This iteration should add:

1. A timeline section in the session detail experience
2. Save-object actions on assistant results

### Timeline panel behavior

The panel should:

- be collapsed by default
- show a compact chronological list
- visually distinguish timeline item kinds

Suggested item labels:

- `Question`
- `Answer`
- `Agent Result`
- `Hypothesis`
- `Discussion`

Each item should show:

- title or short preview
- timestamp when available
- source badge if relevant

### Save-object modal behavior

The modal should be intentionally small:

- title input
- content textarea
- confirm / cancel

No relation editing in this modal for v0.

### Timeline source mapping

Timeline item rendering can use these heuristics:

- transcript items come from the loaded `messages`
- research objects come from the new research object list endpoint
- objects should render as distinct timeline entries, not inline transcript edits

## Backend Module Changes

Expected files:

```text
backend/app/
├── api/
│   └── research_objects.py
├── schemas/
│   └── research_object.py
└── services/
    └── research_object_service.py
```

Existing models should be reused:

- `backend/app/models/research_object.py`

## Frontend Module Changes

Expected files:

```text
frontend/src/
├── pages/
│   └── Session.tsx
├── types/
│   └── research-object.ts
└── locales/
    ├── en-US.json
    └── zh-CN.json
```

If `Session.tsx` becomes too crowded, extract timeline rendering and save-object modal into local components under `frontend/src/components/`.

## Error Handling

The timeline and save flow should degrade gracefully:

- if research object creation fails, show a toast and keep the original answer unchanged
- if timeline fetch fails, keep the session page usable and show an empty/fallback timeline state
- do not block chat, trace, or source loading on research object failures

Errors must not expose secrets or raw backend traces to users.

## Testing Strategy

Backend tests:

- create research object for accessible session
- reject inaccessible session
- reject unsupported type
- list session research objects in chronological order
- preserve source metadata in `content_json`

Frontend checks:

- assistant answer can be saved as `hypothesis`
- assistant answer can be saved as `discussion`
- saved object appears in timeline after success
- agent result can also be promoted
- collapsed timeline does not disrupt session chat workflow

Fast verification:

```bash
pytest tests/test_research_objects_api.py -q
npm run build
```

## Milestone Fit

This iteration closes two remaining gaps from the v0 design:

- notebook-style session timeline
- durable research artifact promotion

It does so without expanding into v1-level workflow complexity.

## Open Questions Resolved

This design locks the following choices:

- timeline lives inside the session page
- no standalone notebook page in this iteration
- only `hypothesis` and `discussion` are user-creatable
- creation is manual, not automatic
- no relation editing UI yet

## Future Extensions

After this iteration, OpenColab can evolve this foundation toward:

- dedicated notebook page
- research object filters and search
- relation authoring UI (`supports`, `contradicts`, `cites`)
- automatic suggestion to save an answer as hypothesis
- experiment objects
- graph visualization

These should build on the same models and session-local workflow rather than replace them.
