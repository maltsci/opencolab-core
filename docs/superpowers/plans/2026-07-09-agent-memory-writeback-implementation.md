# Agent Memory Writeback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users save an agent run into the research memory layer as a `ResearchObject`, with an optional relation that automatically inherits the run trace and citations as evidence.

**Architecture:** Add one dedicated backend `save-memory` API on top of the existing `AgentRun`, `ResearchObject`, and `ResearchObjectRelation` models. Keep the frontend flow inside `Session.tsx` with a small modal that collects object fields and optional relation fields, then updates timeline and relation cache from the single response.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, pytest, React, TypeScript, Ant Design, react-i18next

---

## File Map

- Modify: `backend/app/schemas/agent.py`
- Modify: `backend/app/api/agents.py`
- Modify: `tests/test_agents_api.py`
- Modify: `frontend/src/types/agent.ts`
- Modify: `frontend/src/pages/Session.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`
- Modify: `docs/superpowers/specs/2026-07-09-agent-memory-writeback-design.md`

### Task 1: Add backend save-memory request and response schemas

**Files:**
- Modify: `backend/app/schemas/agent.py`
- Test: `tests/test_agents_api.py`

- [ ] **Step 1: Write failing schema-oriented API test**

```python
@pytest.mark.asyncio
async def test_save_agent_run_to_memory_creates_research_object(...):
    response = await client.post(
        f"/api/v1/agents/runs/{run.id}/save-memory",
        headers=researcher_headers,
        json={
            "type": "hypothesis",
            "title": "Synthesized hypothesis",
            "content": "Agent output text",
            "relation": {"enabled": False},
        },
    )
    assert response.status_code == 201
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest tests/test_agents_api.py -k "save_agent_run_to_memory_creates_research_object" -v`

Expected: FAIL because the route and schemas do not exist yet.

- [ ] **Step 3: Add request / response schemas**

In `backend/app/schemas/agent.py`, add:

```python
class AgentRunSaveMemoryRelationRequest(BaseModel):
    enabled: bool = False
    relation_type: Literal["supports", "contradicts"] | None = None
    target_object_id: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def validate_when_enabled(self) -> "AgentRunSaveMemoryRelationRequest":
        if self.enabled and (not self.relation_type or not self.target_object_id):
            raise ValueError("relation_type and target_object_id are required when relation is enabled")
        return self


class AgentRunSaveMemoryRequest(BaseModel):
    type: Literal["hypothesis", "discussion"]
    title: str | None = None
    content: str
    relation: AgentRunSaveMemoryRelationRequest = Field(default_factory=AgentRunSaveMemoryRelationRequest)


class AgentRunSaveMemoryResponse(BaseModel):
    research_object: ResearchObjectResponse
    relation: ResearchObjectRelationResponse | None = None
```

- [ ] **Step 4: Re-run the focused test**

Run: `backend/.venv/bin/pytest tests/test_agents_api.py -k "save_agent_run_to_memory_creates_research_object" -v`

Expected: still FAIL because the route is not implemented yet.

### Task 2: Implement backend save-memory endpoint

**Files:**
- Modify: `backend/app/api/agents.py`
- Modify: `tests/test_agents_api.py`

- [ ] **Step 1: Add failing behavior tests**

```python
@pytest.mark.asyncio
async def test_save_agent_run_to_memory_creates_relation_with_trace_evidence(...):
    ...
    assert payload["relation"]["metadata_json"]["evidence"]["trace_id"] == trace.id
    assert payload["relation"]["metadata_json"]["evidence"]["citations"][0]["snippet"] == "quoted support"


@pytest.mark.asyncio
async def test_save_agent_run_to_memory_rejects_cross_session_target(...):
    ...
    assert response.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest tests/test_agents_api.py -k "save_agent_run_to_memory" -v`

Expected: FAIL because the route behavior is missing.

- [ ] **Step 3: Implement the route**

In `backend/app/api/agents.py`, add:

```python
@router.post("/runs/{run_id}/save-memory", response_model=AgentRunSaveMemoryResponse, status_code=status.HTTP_201_CREATED)
async def save_agent_run_to_memory(...):
    ...
```

Behavior:

- load the agent run and verify ownership
- resolve the run trace from `agent_run.traces` using the same selection rule as the response schema
- create a new `ResearchObject` with:
  - `type`
  - `title`
  - `content`
  - `created_by = user.id`
  - `content_json = { session_id, origin: "agent_run", agent_run_id, trace_id, source_ids }`
- if `relation.enabled`:
  - load target object
  - verify target object exists
  - verify target object belongs to the same session
  - create `ResearchObjectRelation` with:
    - `relation_type`
    - `created_by = user.id`
    - `created_by_type = "human"`
    - `metadata_json = { confidence: 0.8, evidence: { trace_id, citations, note? } }`
- commit once for the whole action
- return the created object and optional relation

- [ ] **Step 4: Handle atomic failure paths**

Translate:

- missing run -> `404`
- missing target object -> `404`
- cross-session target -> `400`
- duplicate relation -> `409`

Use a single transaction so relation failure rolls back object creation too.

- [ ] **Step 5: Re-run focused backend tests**

Run: `backend/.venv/bin/pytest tests/test_agents_api.py -k "save_agent_run_to_memory" -v`

Expected: PASS

### Task 3: Add frontend request types and modal state

**Files:**
- Modify: `frontend/src/types/agent.ts`
- Modify: `frontend/src/pages/Session.tsx`

- [ ] **Step 1: Add frontend types**

In `frontend/src/types/agent.ts`, add:

```typescript
export interface AgentRunSaveMemoryRequest {
  type: 'hypothesis' | 'discussion';
  title: string;
  content: string;
  relation: {
    enabled: boolean;
    relation_type?: 'supports' | 'contradicts';
    target_object_id?: string;
    note?: string;
  };
}

export interface AgentRunSaveMemoryResponse {
  research_object: SessionResearchObject;
  relation: SessionResearchObjectRelation | null;
}
```

- [ ] **Step 2: Add modal state in Session**

Add state for:

- selected agent message to save
- save-memory modal open/close
- object type
- title draft
- content draft
- relation enabled
- relation type
- relation target
- relation note
- submitting state

- [ ] **Step 3: Run frontend build to verify intentional breakage location**

Run: `cd frontend && npm run build`

Expected: FAIL until the modal UI and submit handler exist.

### Task 4: Add save-memory modal and submit flow

**Files:**
- Modify: `frontend/src/pages/Session.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`

- [ ] **Step 1: Add agent-only action**

On agent result cards, add an action:

```tsx
<Button type="link" size="small" onClick={() => openSaveMemoryModal(msg)}>
  {t('agent.saveToMemory')}
</Button>
```

- [ ] **Step 2: Add modal UI**

Render a small modal with:

- object type select
- title input
- content textarea
- relation enabled switch or checkbox
- conditional relation type select
- conditional target object select
- conditional evidence note textarea

Only show relation inputs when enabled.

- [ ] **Step 3: Implement submit handler**

```typescript
const submitSaveAgentMemory = async () => {
  if (!selectedAgentMessage?.agentRun) return;
  const payload: AgentRunSaveMemoryRequest = { ... };
  const { data } = await apiClient.post<AgentRunSaveMemoryResponse>(
    `/agents/runs/${selectedAgentMessage.agentRun.id}/save-memory`,
    payload,
  );
  setResearchObjects((prev) => [data.research_object, ...prev]);
  if (data.relation) {
    setRelationsByObjectId((prev) => ({
      ...prev,
      [data.research_object.id]: [data.relation],
    }));
  }
  setActiveResearchObjectId(data.research_object.id);
};
```

- [ ] **Step 4: Add i18n copy**

Add keys for:

- `agent.saveToMemory`
- `agent.saveToMemoryTitle`
- `agent.memoryObjectType`
- `agent.memoryRelationToggle`
- `agent.memoryRelationType`
- `agent.memoryRelationTarget`
- `agent.memoryEvidenceNote`
- `agent.memorySaved`
- `agent.memorySaveFailed`

- [ ] **Step 5: Re-run frontend build**

Run: `cd frontend && npm run build`

Expected: PASS

### Task 5: End-to-end regression verification and commit

**Files:**
- Verify only

- [ ] **Step 1: Run focused backend save-memory tests**

Run: `backend/.venv/bin/pytest tests/test_agents_api.py -k "save_agent_run_to_memory" -v`

Expected: PASS

- [ ] **Step 2: Run broader agent API regression**

Run: `backend/.venv/bin/pytest tests/test_agents_api.py -v`

Expected: PASS

- [ ] **Step 3: Run broader research object regression**

Run: `backend/.venv/bin/pytest tests/test_source_extractions.py -k research_object -v`

Expected: PASS

- [ ] **Step 4: Run frontend build**

Run: `cd frontend && npm run build`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/agent.py \
  backend/app/api/agents.py \
  tests/test_agents_api.py \
  frontend/src/types/agent.ts \
  frontend/src/pages/Session.tsx \
  frontend/src/locales/en-US.json \
  frontend/src/locales/zh-CN.json \
  docs/superpowers/specs/2026-07-09-agent-memory-writeback-design.md \
  docs/superpowers/plans/2026-07-09-agent-memory-writeback-implementation.md
git commit -m "feat: add agent memory writeback"
```

## Self-Review

- Spec coverage: the plan covers the dedicated save-memory API, optional relation creation, trace/citation evidence inheritance, modal UI, and immediate timeline update.
- Placeholder scan: no `TBD`, `TODO`, or deferred placeholders remain.
- Type consistency: the plan keeps the current nested relation evidence shape `{ confidence, evidence }`, uses existing session research object types, and avoids introducing a second memory representation.
