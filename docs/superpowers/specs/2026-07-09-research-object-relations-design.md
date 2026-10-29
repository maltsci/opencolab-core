# Research Object Relations v0 Design

## Goal

Add a minimal but extensible relation-editing workflow for session-scoped research objects so a user or future agent can express how one saved hypothesis or discussion relates to another, with uncertainty and evidence attached.

This iteration must stay lightweight enough for the current Session page, but the data model must already point toward a durable "research memory layer" that future agents can read, extend, and reuse.

## Scope

### In scope

- Reuse the existing `ResearchObject` and `ResearchObjectRelation` models
- Keep the first UI workflow focused on two selectable relation types:
  - `supports`
  - `contradicts`
- Do not hardcode relation types into the long-term storage model
- Allow relation editing from a single selected research object
- Keep the interaction inside the existing Session page timeline area
- Allow creating and deleting relations
- Show the currently selected object's outgoing relations
- Add a confidence field to each relation
- Record who or what created the relation
- Attach evidence references to a relation

### Out of scope

- Graph visualization
- Drag-to-connect UI
- Bulk relation editing
- Incoming relation visualization beyond future extensibility
- Full relation taxonomy management UI
- Cross-session or cross-project relations

## Product Shape

This feature should no longer be thought of as only a timeline affordance. The timeline remains the editing surface, but the underlying relation layer is intended to become reusable memory for:

- literature synthesis
- contradiction mining
- hypothesis tracking
- future multi-step agent workflows

That means the UI can stay minimal, but the stored relation record must already preserve enough context for downstream reasoning.

## Session Page Behavior

The existing right-side `Research Timeline` stays as the entry point.

When the user clicks a saved timeline item:

1. The app still scrolls to the original answer and opens the linked trace when available
2. The app also marks that research object as the active object in the timeline panel
3. A new `Object Details` card appears below the timeline list

The timeline list remains compact. Relation editing is not embedded inside every list card.

## Object Details Card

The details card contains three sections:

### 1. Basic information

- object type
- title
- content

### 2. Outgoing relations

Show grouped outgoing relations in the UI. For v0, the UI only needs two visible buckets:

- `Supports`
- `Contradicts`

Each row shows:

- target object title
- target object type
- confidence
- evidence summary when available
- who created it when available
- a small delete action

If no relations exist, show a lightweight empty state.

### 3. Add relation

Controls:

- relation type select:
  - UI initially offers `supports`
  - UI initially offers `contradicts`
- target object select:
  - populated from other research objects in the same session
- confidence input:
  - numeric input in `[0, 1]`
- optional evidence note field
- create button

## Interaction Rules

- Relation direction is always `current object -> target object`
- The user cannot create a relation from an object to itself
- Duplicate `(source_object_id, target_object_id, relation_type)` relations are disallowed
- The target selector excludes the current object
- Relation creation should update the details card immediately after success
- Relation deletion should remove the row immediately after success
- Confidence is required for creation
- `created_by` and `created_by_type` are set by the backend, not entered manually in the v0 UI
- Evidence must be optional in the first UI pass, but the relation schema must support it now

## Data Model

This iteration now requires a schema migration. The relation record should evolve from a thin link table into a lightweight memory entity.

### `ResearchObjectRelation`

Required fields:

- `id`
- `source_object_id`
- `target_object_id`
- `relation_type`
- `metadata_json`
- `created_by`
- `created_by_type`
- `created_at`

### Field intent

#### `relation_type`

The UI for v0 only exposes `supports` and `contradicts`, but the data model must not be coded as if those are the only possible values forever.

That means:

- avoid hardcoding relation logic deep in persistence code
- validate against an allowed set in one place
- make future expansion to `cites`, `extends`, or custom types straightforward

#### `created_by`

Store the creator identity when known.

In v0 this will usually be the current user id.

#### `created_by_type`

Distinguish who or what created the relation.

Recommended initial values:

- `user`
- `agent`
- `system`

The v0 UI will mostly create `human` relations, but the schema must be ready for future agent-authored relations.

#### `metadata_json`

Each relation should optionally carry supporting evidence so it is not just an unsupported label. v0 should keep the flexible JSON field, but the project should standardize one nested shape inside it so both humans and future agents write the same structure.

Recommended v0 structure:

```json
{
  "confidence": 0.72,
  "evidence": {
    "trace_id": "trace-123",
    "citations": [
      {
        "source_id": "source-1",
        "chunk_id": "chunk-1",
        "snippet": "evidence snippet"
      }
    ],
    "note": "Optional user-entered rationale"
  }
}
```

Field intent:

- `confidence`: required float in `[0, 1]`
- `evidence.trace_id`: optional trace link carried over from the answer that motivated the relation
- `evidence.citations`: optional citation payload carried over from that trace
- `evidence.note`: optional human-entered rationale or editing note

This is intentionally flexible enough for v0 while still giving the project a stable shape that future agents can write without guesswork.

### Uniqueness

The existing uniqueness rule should remain:

- `(source_object_id, target_object_id, relation_type)` is unique

## API Design

### List outgoing relations for one research object

`GET /api/v1/research-objects/{id}/relations`

Response shape:

```json
[
  {
    "id": "relation-id",
    "relation_type": "supports",
    "created_by": "user-id",
    "created_by_type": "human",
    "source_object_id": "object-a",
    "target_object_id": "object-b",
    "metadata_json": {
      "confidence": 0.72,
      "evidence": {
        "trace_id": "trace-123",
        "citations": []
      }
    },
    "target_object": {
      "id": "object-b",
      "type": "discussion",
      "title": "Target title"
    },
    "created_at": "2026-07-09T10:00:00Z"
  }
]
```

This endpoint only needs outgoing relations for v0.

### Create relation

`POST /api/v1/research-objects/{id}/relations`

Request:

```json
{
  "relation_type": "supports",
  "target_object_id": "object-b",
  "metadata_json": {
    "confidence": 0.72,
    "evidence": {
      "trace_id": "trace-123",
      "citations": [],
      "note": "The answer cited evidence in favor of this link."
    }
  }
}
```

Behavior:

- verify source object exists and belongs to current user
- verify target object exists and belongs to the same session
- reject self-relations
- reject unsupported relation types for the current configured allowlist
- reject duplicates
- set `created_by` from the authenticated user
- set `created_by_type = "human"` for UI-created relations in v0

Response:

```json
{
  "id": "relation-id",
  "relation_type": "supports",
  "created_by": "user-id",
  "created_by_type": "human",
  "source_object_id": "object-a",
  "target_object_id": "object-b",
  "metadata_json": {
    "confidence": 0.72,
    "evidence": {
      "trace_id": "trace-123",
      "citations": []
    }
  },
  "target_object": {
    "id": "object-b",
    "type": "discussion",
    "title": "Target title"
  },
  "created_at": "2026-07-09T10:00:00Z"
}
```

### Delete relation

`DELETE /api/v1/research-object-relations/{id}`

Behavior:

- only allow deletion when the current user owns the source object

Response:

- `204 No Content`

## Backend Design

## Routing

Add a dedicated relation API surface rather than overloading the existing session endpoints.

Recommended backend additions:

- `backend/app/api/research_object_relations.py`
- `backend/app/schemas/research_object_relation.py`
- migration updating `research_object_relations`

## Relation Type Configuration

The user is right that relation types should not be effectively hardcoded into the product.

For v0, the recommended compromise is:

- store `relation_type` as a string column
- validate against a backend allowlist defined in one central module
- expose only `supports` and `contradicts` in the first UI

This gives near-term safety without freezing the model shape.

## Evidence Handling

The relation should link to evidence even in v0.

Recommended v0 rule:

- when a relation is created from a timeline object that came from an answer with a trace, prefill `metadata_json.evidence.trace_id`
- optionally carry over trace citations into `metadata_json.evidence.citations`
- allow the user to add a short rationale note in `metadata_json.evidence.note`

This makes the relation auditable and more useful for future agents.

## Ownership and Safety

For v0, relation editing follows the same ownership assumption as the current research object editing flow:

- source object must be owned by the current user
- target object must be visible within the same session

This keeps the authorization rule simple and aligned with the current local-first workflow.

## Frontend Design

## State

Extend the Session page with:

- `activeResearchObjectId`
- `relationsByObjectId`
- loading state for relation fetches
- form state for the selected relation type and target object
- form state for confidence
- optional evidence summary state

## UI Placement

Inside the existing right-side timeline panel:

1. `Research Timeline` list
2. `Object Details` card for the selected item
3. Existing trace / citation cards remain below or alongside depending on the current layout

The important constraint is that relation editing belongs to the selected research object details, not to the main message list and not to every timeline card.

## UI Constraints for v0

To keep the UI manageable:

- relation type picker only shows `supports` and `contradicts`
- confidence is a required numeric field or slider
- evidence entry can be lightweight, such as:
  - auto-filled trace reference
  - read-only carried-over citations
  - optional rationale note

## Error Handling

Show user-facing errors for:

- trying to relate an object to itself
- duplicate relation creation
- target object no longer available
- invalid confidence range
- backend request failures

Use existing Ant Design message / modal feedback patterns.

## Testing

### Backend

Add tests for:

- list outgoing relations
- create relation successfully
- reject self relation
- reject duplicate relation
- delete relation successfully
- persist confidence
- persist created_by and created_by_type
- persist evidence payload under `metadata_json.evidence`

### Frontend

At minimum, verify:

- Session page still builds cleanly
- selecting a timeline object opens the details section
- creating or deleting relations updates state correctly
- confidence is required
- relation rows display confidence and evidence summary when present

## Why This Is the Right v0

This design keeps the feature aligned with the project's current maturity while also making it more foundational:

- small enough to implement quickly
- expressive enough to start capturing research logic
- structured enough to become long-term agent memory
- avoids premature graph UI complexity
- extends naturally toward future research object graphs, richer relation types, and reusable hypothesis networks

It also matches the product direction already established in the session timeline work: the system is not just saving answers, it is beginning to preserve the structure of scientific reasoning.
