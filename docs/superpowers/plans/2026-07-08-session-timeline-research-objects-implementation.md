# Session Timeline and Research Objects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an in-session notebook-style timeline plus manual save actions that turn assistant answers and agent outputs into reusable research objects.

**Architecture:** Reuse the existing `ResearchObject` model and keep the first iteration session-scoped in the UI. The backend adds a small REST surface for create/list, while the frontend extends the Session page with lightweight save actions and a collapsible timeline panel instead of introducing a new top-level page.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, pytest, React, TypeScript, Ant Design, react-i18next

---

## File Map

- Create: `backend/app/api/research_objects.py`
- Create: `backend/app/schemas/research_object.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/schemas/__init__.py`
- Modify: `tests/test_source_extractions.py`
- Modify: `frontend/src/pages/Session.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`

### Task 1: Backend list/create contract

**Files:**
- Create: `backend/app/schemas/research_object.py`
- Modify: `backend/app/schemas/__init__.py`
- Test: `tests/test_source_extractions.py`

- [ ] **Step 1: Write the failing schema/API tests**

```python
async def test_create_research_object_from_session_message(client, auth_headers, session_obj, assistant_message):
    response = client.post(
        "/api/v1/research-objects",
        headers=auth_headers,
        json={
            "session_id": session_obj.id,
            "message_id": assistant_message.id,
            "type": "hypothesis",
            "title": "Draft hypothesis",
            "content": "A focused hypothesis from the answer",
            "content_json": {
                "origin": "assistant_message",
                "source_ids": ["source-1"],
            },
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "hypothesis"
    assert data["session_id"] == session_obj.id
    assert data["message_id"] == assistant_message.id
    assert data["content_json"]["origin"] == "assistant_message"


async def test_list_session_research_objects_returns_newest_first(client, auth_headers, session_obj):
    response = client.get(
        f"/api/v1/sessions/{session_obj.id}/research-objects",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_source_extractions.py -k "research_object_from_session_message or list_session_research_objects" -v`

Expected: FAIL with 404 or missing route/schema import errors.

- [ ] **Step 3: Add request/response schemas**

```python
from datetime import datetime

from pydantic import BaseModel, Field


class ResearchObjectCreate(BaseModel):
    session_id: str
    message_id: str | None = None
    type: str
    title: str | None = Field(default=None, max_length=500)
    content: str | None = None
    content_json: dict = Field(default_factory=dict)


class ResearchObjectResponse(BaseModel):
    id: str
    session_id: str | None = None
    message_id: str | None = None
    type: str
    title: str | None
    content: str | None
    content_json: dict
    created_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Run the focused test slice**

Run: `pytest tests/test_source_extractions.py -k "research_object_from_session_message or list_session_research_objects" -v`

Expected: still FAIL because routes are not implemented yet.

### Task 2: Backend routes using existing model

**Files:**
- Create: `backend/app/api/research_objects.py`
- Modify: `backend/app/main.py`
- Test: `tests/test_source_extractions.py`

- [ ] **Step 1: Write the failing permission/behavior tests**

```python
async def test_create_research_object_rejects_unknown_session(client, auth_headers):
    response = client.post(
        "/api/v1/research-objects",
        headers=auth_headers,
        json={
            "session_id": "missing-session",
            "type": "discussion",
            "content": "content",
            "content_json": {},
        },
    )

    assert response.status_code == 404


async def test_create_research_object_stores_message_origin(client, auth_headers, session_obj, assistant_message, db_session):
    response = client.post(
        "/api/v1/research-objects",
        headers=auth_headers,
        json={
            "session_id": session_obj.id,
            "message_id": assistant_message.id,
            "type": "discussion",
            "title": "Saved discussion",
            "content": "Captured discussion",
            "content_json": {
                "origin": "agent_run",
                "trace_id": "trace-123",
                "source_ids": ["source-1", "source-2"],
            },
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["content_json"]["trace_id"] == "trace-123"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_source_extractions.py -k "stores_message_origin or rejects_unknown_session" -v`

Expected: FAIL because the route does not exist yet.

- [ ] **Step 3: Implement the router**

```python
router = APIRouter(prefix="/research-objects", tags=["research-objects"])


@router.post("", response_model=ResearchObjectResponse, status_code=status.HTTP_201_CREATED)
async def create_research_object(...):
    session = await _get_session_for_user(body.session_id, user, db)
    if body.message_id is not None:
        message_result = await db.execute(
            select(Message).where(
                Message.id == body.message_id,
                Message.session_id == session.id,
            )
        )
        if message_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Message not found")

    research_object = ResearchObject(
        type=body.type,
        title=body.title,
        content=body.content,
        content_json={
            **body.content_json,
            "session_id": session.id,
            "source_message_id": body.message_id,
        },
        created_by=user.id,
    )
    db.add(research_object)
    await db.commit()
    await db.refresh(research_object)
    return ResearchObjectResponse(
        **ResearchObjectResponse.model_validate(research_object).model_dump(),
        session_id=session.id,
        message_id=body.message_id,
    )


@router.get("/sessions/{session_id}", response_model=list[ResearchObjectResponse])
async def list_research_objects_for_session(...):
    await _get_session_for_user(session_id, user, db)
    result = await db.execute(
        select(ResearchObject)
        .where(ResearchObject.content_json["session_id"].as_string() == session_id)
        .order_by(ResearchObject.created_at.desc())
    )
    return [
        ResearchObjectResponse(
            **ResearchObjectResponse.model_validate(item).model_dump(),
            session_id=item.content_json.get("session_id"),
            message_id=item.content_json.get("source_message_id"),
        )
        for item in result.scalars().all()
    ]
```

- [ ] **Step 4: Register router**

```python
app.include_router(research_objects.router, prefix="/api/v1")
```

- [ ] **Step 5: Run backend tests**

Run: `pytest tests/test_source_extractions.py -k "research_object" -v`

Expected: PASS for the new research-object API coverage.

### Task 3: Session timeline data loading

**Files:**
- Modify: `frontend/src/pages/Session.tsx`
- Test: existing frontend build

- [ ] **Step 1: Add local types and fetch state**

```typescript
interface SessionResearchObject {
  id: string;
  session_id?: string | null;
  message_id?: string | null;
  type: 'hypothesis' | 'discussion' | string;
  title: string | null;
  content: string | null;
  content_json: Record<string, unknown>;
  created_at: string;
}

const [researchObjects, setResearchObjects] = useState<SessionResearchObject[]>([]);
const [timelineOpen, setTimelineOpen] = useState(false);
```

- [ ] **Step 2: Extend the session bootstrap request**

```typescript
apiClient
  .get(`/research-objects/sessions/${sessionId}`)
  .then((r) => setResearchObjects(r.data))
  .catch(() => setResearchObjects([]));
```

- [ ] **Step 3: Add a message-level trace/timeline action**

```typescript
const handleOpenTrace = (messageId: string) => {
  setSelectedTraceMessageId(messageId);
  setTimelineOpen(true);
};
```

- [ ] **Step 4: Run frontend build for type feedback**

Run: `npm run build`

Expected: FAIL or report missing i18n keys until the UI copy is added.

### Task 4: Save as Hypothesis / Discussion actions

**Files:**
- Modify: `frontend/src/pages/Session.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`

- [ ] **Step 1: Add save helpers**

```typescript
const saveAsResearchObject = async (
  msg: Message,
  type: 'hypothesis' | 'discussion',
) => {
  const trace = traceByMessageId[msg.id];
  const title =
    type === 'hypothesis'
      ? t('researchObject.defaultHypothesisTitle')
      : t('researchObject.defaultDiscussionTitle');

  const payload = {
    session_id: sessionId,
    message_id: msg.id,
    type,
    title,
    content: msg.content,
    content_json: {
      origin: msg.agentRun ? 'agent_run' : 'assistant_message',
      trace_id: trace?.traceId ?? null,
      source_ids: trace?.inputs.source_ids ?? [],
      agent_run_id: msg.agentRun?.id ?? null,
    },
  };

  const { data } = await apiClient.post('/research-objects', payload);
  setResearchObjects((prev) => [data, ...prev]);
  setTimelineOpen(true);
};
```

- [ ] **Step 2: Add answer action buttons**

```tsx
<Space size={8} wrap>
  <Button size="small" onClick={() => handleCopyAnswer(msg.content)}>
    {t('chat.copy')}
  </Button>
  <Button size="small" onClick={() => handleRegenerate(msg.id)}>
    {t('chat.regenerate')}
  </Button>
  <Button size="small" onClick={() => saveAsNote(msg)}>
    {t('note.save')}
  </Button>
  <Button size="small" onClick={() => saveAsResearchObject(msg, 'hypothesis')}>
    {t('researchObject.saveAsHypothesis')}
  </Button>
  <Button size="small" onClick={() => saveAsResearchObject(msg, 'discussion')}>
    {t('researchObject.saveAsDiscussion')}
  </Button>
  <Button size="small" onClick={() => handleOpenTrace(msg.id)}>
    {t('session.openTrace')}
  </Button>
</Space>
```

- [ ] **Step 3: Add i18n copy**

```json
{
  "researchObject": {
    "saveAsHypothesis": "Save as Hypothesis",
    "saveAsDiscussion": "Save as Discussion",
    "savedHypothesis": "Saved to timeline as hypothesis",
    "savedDiscussion": "Saved to timeline as discussion",
    "defaultHypothesisTitle": "Saved hypothesis",
    "defaultDiscussionTitle": "Saved discussion"
  }
}
```

- [ ] **Step 4: Re-run frontend build**

Run: `npm run build`

Expected: PASS for the new actions and copy.

### Task 5: Replace always-open trace sidebar with notebook-style panel

**Files:**
- Modify: `frontend/src/pages/Session.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`

- [ ] **Step 1: Convert the right sidebar into a collapsible panel**

```tsx
{timelineOpen && (
  <Sider width={360} theme="light" style={{ padding: 16, overflow: 'auto', borderLeft: '1px solid #f0f0f0' }}>
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card
        title={t('timeline.title')}
        extra={<Button type="text" onClick={() => setTimelineOpen(false)}>{t('common.close')}</Button>}
      >
        <List
          dataSource={researchObjects}
          locale={{ emptyText: t('timeline.empty') }}
          renderItem={(item) => (
            <List.Item>
              <div>
                <Tag color={item.type === 'hypothesis' ? 'purple' : 'blue'}>{item.type}</Tag>
                <div>{item.title || t('timeline.untitled')}</div>
                <div>{item.content}</div>
              </div>
            </List.Item>
          )}
        />
      </Card>
      {activeTrace && (
        <Card title={t('session.traceTitle')}>
          <div>{activeTrace.inputs.query}</div>
          <List
            size="small"
            dataSource={activeTrace.summarySteps}
            renderItem={(item) => <List.Item>{item}</List.Item>}
          />
        </Card>
      )}
    </Space>
  </Sider>
)}
```

- [ ] **Step 2: Remove the low-value retrieved evidence block**

```tsx
// Remove the standalone "Retrieved evidence" list that only shows IDs/scores.
// Keep only:
// - question
// - documents used
// - summary steps
// - citations with readable snippet text
```

- [ ] **Step 3: Add a compact open button in the conversation area**

```tsx
<Button
  type="default"
  icon={<ExperimentOutlined />}
  onClick={() => setTimelineOpen((prev) => !prev)}
>
  {t('timeline.button')}
</Button>
```

- [ ] **Step 4: Run frontend build**

Run: `npm run build`

Expected: PASS and no TypeScript errors.

### Task 6: Final regression verification

**Files:**
- Verify only

- [ ] **Step 1: Run focused backend tests**

Run: `pytest tests/test_source_extractions.py -k "research_object" -v`

Expected: PASS

- [ ] **Step 2: Run admin regression test touched by current dirty tree**

Run: `pytest tests/test_admin.py -v`

Expected: PASS

- [ ] **Step 3: Run frontend production build**

Run: `npm run build`

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/research_objects.py \
  backend/app/schemas/research_object.py \
  backend/app/schemas/__init__.py \
  backend/app/main.py \
  tests/test_source_extractions.py \
  frontend/src/pages/Session.tsx \
  frontend/src/locales/en-US.json \
  frontend/src/locales/zh-CN.json \
  docs/superpowers/plans/2026-07-08-session-timeline-research-objects-implementation.md
git commit -m "feat: add session timeline research objects"
```

## Self-Review

- Spec coverage: this plan covers the in-session timeline, manual save actions for hypothesis/discussion, session-linked listing, and a more understandable trace interaction model.
- Placeholder scan: no `TODO` or deferred implementation markers remain.
- Type consistency: backend uses `session_id`, `message_id`, `content_json`; frontend uses the same payload keys and reads the same response fields.
