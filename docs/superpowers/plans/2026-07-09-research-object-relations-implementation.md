# Research Object Relations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add session-scoped research object relations as a durable scientific reasoning memory layer, with extensible relation types, creator metadata, and evidence metadata.

**Architecture:** Extend `ResearchObjectRelation` from a thin edge table into a lightweight memory record. Backend APIs manage outgoing relations for a selected research object, while the Session UI uses focused details components instead of bloating the page-level container.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic v2, pytest, React, TypeScript, Ant Design, react-i18next

---

## File Map

- Create: `backend/app/api/research_object_relations.py`
- Create: `backend/app/schemas/research_object_relation.py`
- Create: `backend/alembic/versions/<revision>_expand_research_object_relations.py`
- Create: `frontend/src/components/research/ResearchObjectDetails.tsx`
- Create: `frontend/src/components/research/ResearchRelationEditor.tsx`
- Modify: `backend/app/main.py`
- Modify: `backend/app/models/research_object.py`
- Modify: `tests/test_source_extractions.py`
- Modify: `frontend/src/pages/Session.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`

### Task 1: Expand relation model with memory metadata

**Files:**
- Modify: `backend/app/models/research_object.py`
- Create: `backend/alembic/versions/<revision>_expand_research_object_relations.py`
- Test: `tests/test_source_extractions.py`

- [ ] **Step 1: Write failing model tests**

```python
def test_research_object_relation_persists_metadata_shape():
    relation = ResearchObjectRelation(
        relation_type="supports",
        metadata_json={"confidence": 0.8, "reason": "matches cited claim"},
        created_by_type="human",
    )
    assert relation.metadata_json["confidence"] == 0.8


async def test_research_object_relation_direction_is_outgoing_only(...):
    response = await client.get(
        f"/api/v1/research-objects/{target_object.id}/relations",
        headers=researcher_headers,
    )
    assert response.status_code == 200
    assert response.json() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_source_extractions.py -k "metadata_shape or direction_is_outgoing_only" -v`

Expected: FAIL because the fields and relation endpoint support are not implemented.

- [ ] **Step 3: Update ORM model**

```python
metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
created_by: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
created_by_type: Mapped[str] = mapped_column(String(32), default="human", server_default="human")
```

Keep:

- `relation_type` as `String(32)` with no database enum
- unique constraint on `(source_object_id, target_object_id, relation_type)`

- [ ] **Step 4: Add migration**

Migration adds:

- `metadata_json`
- `created_by`
- `created_by_type`

with safe defaults for existing rows.

- [ ] **Step 5: Run the focused test slice**

Run: `pytest tests/test_source_extractions.py -k "metadata_shape or direction_is_outgoing_only" -v`

Expected: still FAIL because the API layer is not in place yet.

### Task 2: Backend relation schemas and allowlist

**Files:**
- Create: `backend/app/schemas/research_object_relation.py`
- Test: `tests/test_source_extractions.py`

- [ ] **Step 1: Write failing API validation tests**

```python
async def test_create_research_object_relation_rejects_unknown_relation_type(...):
    response = await client.post(
        f"/api/v1/research-objects/{source_object.id}/relations",
        headers=researcher_headers,
        json={
            "relation_type": "extends",
            "target_object_id": target_object.id,
            "metadata_json": {"confidence": 0.8},
        },
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_source_extractions.py -k "unknown_relation_type" -v`

Expected: FAIL because the relation schema does not exist yet.

- [ ] **Step 3: Add schemas**

```python
ALLOWED_RELATION_TYPES = ("supports", "contradicts")


class ResearchObjectRelationCreate(BaseModel):
    relation_type: Literal["supports", "contradicts"]
    target_object_id: str
    metadata_json: dict = Field(default_factory=dict)


class ResearchObjectRelationTarget(BaseModel):
    id: str
    type: str
    title: str | None


class ResearchObjectRelationResponse(BaseModel):
    id: str
    relation_type: str
    source_object_id: str
    target_object_id: str
    metadata_json: dict
    created_by: str | None
    created_by_type: str
    target_object: ResearchObjectRelationTarget
    created_at: datetime
```

- [ ] **Step 4: Re-run the focused test**

Run: `pytest tests/test_source_extractions.py -k "unknown_relation_type" -v`

Expected: still FAIL because routes are missing.

### Task 3: Relation API routes

**Files:**
- Create: `backend/app/api/research_object_relations.py`
- Modify: `backend/app/main.py`
- Test: `tests/test_source_extractions.py`

- [ ] **Step 1: Expand tests for success and permissions**

```python
async def test_list_research_object_relations_returns_outgoing_relations(...):
    ...


async def test_create_research_object_relation_persists_metadata_and_creator(...):
    assert payload["metadata_json"]["confidence"] == 0.8
    assert payload["created_by"] == researcher_user.id
    assert payload["created_by_type"] == "human"


async def test_create_research_object_relation_rejects_self_relation(...):
    assert response.status_code == 400


async def test_create_research_object_relation_rejects_duplicate(...):
    assert response.status_code == 409


async def test_delete_research_object_relation_returns_403_for_non_owner(...):
    assert response.status_code == 403


async def test_delete_research_object_relation_returns_404_for_missing_relation(...):
    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_source_extractions.py -k "research_object_relation_" -v`

Expected: FAIL because the routes are missing.

- [ ] **Step 3: Implement list/create/delete routes**

```python
@router.get("/research-objects/{research_object_id}/relations", response_model=list[ResearchObjectRelationResponse])
async def list_research_object_relations(...):
    ...


@router.post("/research-objects/{research_object_id}/relations", response_model=ResearchObjectRelationResponse, status_code=status.HTTP_201_CREATED)
async def create_research_object_relation(...):
    ...


@router.delete("/research-object-relations/{relation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_research_object_relation(...):
    ...
```

Rules:

- source object must belong to current user
- target object must be a different object
- target object must belong to the same session as the source object
- duplicates return `409`
- missing relation returns `404`
- existing relation owned by another source owner returns `403`
- set `created_by = user.id`
- set `created_by_type = "human"`

- [ ] **Step 4: Register the router**

```python
app.include_router(research_object_relations_router, prefix=api)
```

- [ ] **Step 5: Run backend relation tests**

Run: `pytest tests/test_source_extractions.py -k "research_object_relation_" -v`

Expected: PASS

### Task 4: Split Session page research details UI

**Files:**
- Create: `frontend/src/components/research/ResearchObjectDetails.tsx`
- Create: `frontend/src/components/research/ResearchRelationEditor.tsx`
- Modify: `frontend/src/pages/Session.tsx`

- [ ] **Step 1: Add local types in Session page**

```typescript
interface SessionResearchObjectRelation {
  id: string;
  relation_type: 'supports' | 'contradicts';
  source_object_id: string;
  target_object_id: string;
  metadata_json: Record<string, unknown>;
  created_by: string | null;
  created_by_type: string;
  target_object: {
    id: string;
    type: string;
    title: string | null;
  };
  created_at: string;
}
```

- [ ] **Step 2: Add selected object and relations state**

```typescript
const [activeResearchObjectId, setActiveResearchObjectId] = useState<string | null>(null);
const [relationsByObjectId, setRelationsByObjectId] = useState<Record<string, SessionResearchObjectRelation[]>>({});
```

- [ ] **Step 3: Extract object details component**

`ResearchObjectDetails.tsx` should render:

- title
- type
- content
- grouped outgoing relations
- editor section mount point

- [ ] **Step 4: Extract relation editor component**

`ResearchRelationEditor.tsx` should render:

- relation type select
- target object select
- optional rationale input
- confidence input bound to metadata
- submit action

- [ ] **Step 5: Run frontend build**

Run: `npm run build`

Expected: FAIL until handlers and i18n are connected.

### Task 5: Frontend relation fetch/create/delete flow

**Files:**
- Modify: `frontend/src/pages/Session.tsx`
- Modify: `frontend/src/components/research/ResearchObjectDetails.tsx`
- Modify: `frontend/src/components/research/ResearchRelationEditor.tsx`

- [ ] **Step 1: Add fetch helper**

```typescript
const loadResearchObjectRelations = async (objectId: string) => {
  const { data } = await apiClient.get<SessionResearchObjectRelation[]>(
    `/research-objects/${objectId}/relations`,
  );
  setRelationsByObjectId((prev) => ({ ...prev, [objectId]: data }));
};
```

- [ ] **Step 2: Add selected timeline item handler**

```typescript
const handleSelectResearchObject = (item: SessionResearchObject) => {
  setActiveResearchObjectId(item.id);
  void loadResearchObjectRelations(item.id);
  if (item.message_id) handleOpenTrace(item.message_id);
};
```

- [ ] **Step 3: Add create relation handler**

```typescript
const submitRelationCreate = async (payload: RelationEditorSubmit) => {
  if (!activeResearchObjectId) return;
  const { data } = await apiClient.post<SessionResearchObjectRelation>(
    `/research-objects/${activeResearchObjectId}/relations`,
    payload,
  );
  setRelationsByObjectId((prev) => ({
    ...prev,
    [activeResearchObjectId]: [...(prev[activeResearchObjectId] || []), data],
  }));
};
```

- [ ] **Step 4: Add delete relation handler**

```typescript
const deleteRelation = async (relationId: string) => {
  if (!activeResearchObjectId) return;
  await apiClient.delete(`/research-object-relations/${relationId}`);
  setRelationsByObjectId((prev) => ({
    ...prev,
    [activeResearchObjectId]: (prev[activeResearchObjectId] || []).filter((item) => item.id !== relationId),
  }));
};
```

- [ ] **Step 5: Show confidence and evidence summary**

Display from `metadata_json`:

- confidence
- note
- trace_id when present

- [ ] **Step 6: Re-run frontend build**

Run: `npm run build`

Expected: PASS

### Task 6: Copy and regression verification

**Files:**
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`
- Verify only

- [ ] **Step 1: Add i18n copy**

Add keys for:

- object details
- supports / contradicts groups
- relation type
- target object
- confidence
- rationale note
- add relation
- relation deleted
- relation created
- no relations yet

- [ ] **Step 2: Run focused backend relation tests**

Run: `pytest tests/test_source_extractions.py -k "research_object_relation_" -v`

Expected: PASS

- [ ] **Step 3: Run broader research object regression**

Run: `pytest tests/test_source_extractions.py -k research_object -v`

Expected: PASS

- [ ] **Step 4: Run frontend build**

Run: `npm run build`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/research_object_relations.py \
  backend/app/schemas/research_object_relation.py \
  backend/alembic/versions/<revision>_expand_research_object_relations.py \
  backend/app/main.py \
  backend/app/models/research_object.py \
  tests/test_source_extractions.py \
  frontend/src/components/research/ResearchObjectDetails.tsx \
  frontend/src/components/research/ResearchRelationEditor.tsx \
  frontend/src/pages/Session.tsx \
  frontend/src/locales/en-US.json \
  frontend/src/locales/zh-CN.json \
  docs/superpowers/plans/2026-07-09-research-object-relations-implementation.md
git commit -m "feat: add research object relations"
```

## Self-Review

- Spec coverage: this plan covers extensible relation typing, memory metadata, creator metadata, directionality, and selected-object relation editing UI.
- Placeholder scan: no `TBD`, `TODO`, or deferred requirement placeholders remain.
- Type consistency: relation types remain string-backed in storage, UI still limits to `supports` and `contradicts`, and metadata is consistently carried as `metadata_json`.
