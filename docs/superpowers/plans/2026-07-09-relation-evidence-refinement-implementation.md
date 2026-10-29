# Relation Evidence Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refine research object relations so each relation stores and displays a stable evidence payload composed of trace references, citations, and a human rationale note.

**Architecture:** Keep `ResearchObjectRelation.metadata_json` as the storage surface, but standardize its shape to `{ confidence, evidence }`. Backend schemas and routes validate and normalize that payload, while the Session research details UI renders a readable evidence summary instead of exposing raw trace metadata directly.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, pytest, React, TypeScript, Ant Design, react-i18next

---

## File Map

- Modify: `backend/app/schemas/research_object_relation.py`
- Modify: `backend/app/api/research_object_relations.py`
- Modify: `tests/test_source_extractions.py`
- Modify: `frontend/src/components/research/types.ts`
- Modify: `frontend/src/components/research/ResearchRelationEditor.tsx`
- Modify: `frontend/src/components/research/ResearchObjectDetails.tsx`
- Modify: `frontend/src/pages/Session.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`
- Modify: `docs/superpowers/specs/2026-07-09-research-object-relations-design.md`

### Task 1: Standardize the backend evidence payload shape

**Files:**
- Modify: `backend/app/schemas/research_object_relation.py`
- Modify: `backend/app/api/research_object_relations.py`
- Test: `tests/test_source_extractions.py`

- [ ] **Step 1: Write failing schema tests**

```python
async def test_create_research_object_relation_persists_nested_evidence_payload(...):
    response = await client.post(
        f"/api/v1/research-objects/{source_object.id}/relations",
        headers=researcher_headers,
        json={
            "relation_type": "supports",
            "target_object_id": target_object.id,
            "metadata_json": {
                "confidence": 0.8,
                "evidence": {
                    "trace_id": "trace-123",
                    "citations": [{"source_id": "source-1", "snippet": "quoted support"}],
                    "note": "User confirmed the rationale",
                },
            },
        },
    )
    payload = response.json()
    assert payload["metadata_json"]["evidence"]["trace_id"] == "trace-123"
    assert payload["metadata_json"]["evidence"]["note"] == "User confirmed the rationale"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest tests/test_source_extractions.py -k "nested_evidence_payload" -v`

Expected: FAIL because the nested evidence shape is not enforced consistently yet.

- [ ] **Step 3: Tighten request and response schemas**

Add small typed helpers in `backend/app/schemas/research_object_relation.py`:

```python
class ResearchRelationCitation(BaseModel):
    source_id: str | None = None
    chunk_id: str | None = None
    snippet: str | None = None
    score: float | None = None


class ResearchRelationEvidence(BaseModel):
    trace_id: str | None = None
    citations: list[ResearchRelationCitation] = Field(default_factory=list)
    note: str | None = None


class ResearchRelationMetadata(BaseModel):
    confidence: float = Field(ge=0, le=1)
    evidence: ResearchRelationEvidence = Field(default_factory=ResearchRelationEvidence)
```

Use that in:

```python
class ResearchObjectRelationCreate(BaseModel):
    relation_type: Literal["supports", "contradicts"]
    target_object_id: str
    metadata_json: ResearchRelationMetadata
```

- [ ] **Step 4: Normalize stored metadata in the route**

In `backend/app/api/research_object_relations.py`, persist:

```python
metadata_json=body.metadata_json.model_dump()
```

and return the same normalized structure in the response serializer.

- [ ] **Step 5: Re-run the focused backend test**

Run: `backend/.venv/bin/pytest tests/test_source_extractions.py -k "nested_evidence_payload" -v`

Expected: PASS

### Task 2: Preserve carried-over trace and citations on relation creation

**Files:**
- Modify: `frontend/src/components/research/types.ts`
- Modify: `frontend/src/pages/Session.tsx`
- Test: `tests/test_source_extractions.py`

- [ ] **Step 1: Add a failing API test for evidence passthrough**

```python
async def test_create_research_object_relation_keeps_citations_in_evidence(...):
    ...
    assert payload["metadata_json"]["evidence"]["citations"][0]["snippet"] == "quoted support"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest tests/test_source_extractions.py -k "keeps_citations_in_evidence" -v`

Expected: FAIL because the old flat metadata shape still leaks through.

- [ ] **Step 3: Update shared frontend types**

In `frontend/src/components/research/types.ts`, change the submit payload to:

```typescript
export interface ResearchRelationSubmitPayload {
  relation_type: 'supports' | 'contradicts';
  target_object_id: string;
  metadata_json: {
    confidence: number;
    evidence: {
      trace_id?: string;
      citations: Array<Record<string, unknown>>;
      note?: string;
    };
  };
}
```

- [ ] **Step 4: Update relation creation in Session**

In `frontend/src/pages/Session.tsx`, build the request as:

```typescript
const requestPayload = {
  ...payload,
  metadata_json: {
    confidence: payload.metadata_json.confidence,
    evidence: {
      ...payload.metadata_json.evidence,
      ...(trace?.traceId ? { trace_id: trace.traceId } : {}),
      citations: trace?.citations || payload.metadata_json.evidence.citations || [],
    },
  },
};
```

This keeps auto-carried trace evidence in one stable place.

- [ ] **Step 5: Re-run the focused API test**

Run: `backend/.venv/bin/pytest tests/test_source_extractions.py -k "keeps_citations_in_evidence" -v`

Expected: PASS

### Task 3: Make the relation editor explicitly about evidence

**Files:**
- Modify: `frontend/src/components/research/ResearchRelationEditor.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`

- [ ] **Step 1: Update the editor payload shape**

Change the submit payload builder in `ResearchRelationEditor.tsx` to emit:

```typescript
metadata_json: {
  confidence: Number(confidence),
  evidence: {
    citations: [],
    ...(note.trim() ? { note: note.trim() } : {}),
  },
},
```

- [ ] **Step 2: Adjust copy to match the product language**

Add or update keys for:

- `relations.evidence`
- `relations.evidenceNote`
- `relations.evidenceNotePlaceholder`
- `relations.evidenceFromTrace`
- `relations.evidenceFromCitations`

- [ ] **Step 3: Run frontend build to catch type mismatches**

Run: `cd frontend && npm run build`

Expected: FAIL until the details renderer also understands the nested evidence shape.

### Task 4: Replace raw metadata rendering with readable evidence summaries

**Files:**
- Modify: `frontend/src/components/research/ResearchObjectDetails.tsx`
- Modify: `frontend/src/components/research/types.ts`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`

- [ ] **Step 1: Add lightweight readers for nested evidence**

In `ResearchObjectDetails.tsx`, add helpers:

```typescript
function readEvidence(metadataJson: Record<string, unknown>) {
  const evidence = metadataJson.evidence;
  return evidence && typeof evidence === 'object'
    ? evidence as Record<string, unknown>
    : {};
}
```

and then derive:

- `confidence`
- `evidence.note`
- `evidence.trace_id`
- `evidence.citations`

- [ ] **Step 2: Render an evidence summary instead of raw trace-oriented details**

Per relation row:

- show the first useful citation snippet when available
- otherwise show the evidence note
- show a compact "from trace" indicator when `trace_id` exists
- show a compact citation count tag when citations exist

Do not expose raw chunk ids unless no better evidence summary exists.

- [ ] **Step 3: Re-run frontend build**

Run: `cd frontend && npm run build`

Expected: PASS

### Task 5: Regression verification and commit

**Files:**
- Verify only

- [ ] **Step 1: Run focused relation backend tests**

Run: `backend/.venv/bin/pytest tests/test_source_extractions.py -k "research_object_relation_" -v`

Expected: PASS

- [ ] **Step 2: Run broader research object regression**

Run: `backend/.venv/bin/pytest tests/test_source_extractions.py -k research_object -v`

Expected: PASS

- [ ] **Step 3: Run frontend build**

Run: `cd frontend && npm run build`

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/research_object_relation.py \
  backend/app/api/research_object_relations.py \
  tests/test_source_extractions.py \
  frontend/src/components/research/types.ts \
  frontend/src/components/research/ResearchRelationEditor.tsx \
  frontend/src/components/research/ResearchObjectDetails.tsx \
  frontend/src/pages/Session.tsx \
  frontend/src/locales/en-US.json \
  frontend/src/locales/zh-CN.json \
  docs/superpowers/specs/2026-07-09-research-object-relations-design.md \
  docs/superpowers/plans/2026-07-09-relation-evidence-refinement-implementation.md
git commit -m "feat: refine relation evidence payload"
```

## Self-Review

- Spec coverage: the plan covers the agreed v0 shape of `trace + citations + human note`, keeps the current storage model, and upgrades the UI from raw trace fields to readable evidence summaries.
- Placeholder scan: no `TBD`, `TODO`, or deferred implementation notes remain.
- Type consistency: the same nested `metadata_json.evidence` structure is used in backend schemas, API persistence, frontend submit payloads, rendering, and tests.
