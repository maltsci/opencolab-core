# Research Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a lightweight deterministic agent runtime with two built-in research agents, persistent run records, trace/citation support, and minimal session UI entry points.

**Architecture:** Extend the current FastAPI + PostgreSQL + Qdrant stack with a small `AgentRun` persistence model and a service-layer runtime that reuses existing retrieval, LLM, citation, and trace plumbing. Keep agent execution synchronous in the request path for v0 and expose results through simple REST endpoints plus session UI rendering.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic v2, PostgreSQL JSON columns, existing LiteLLM integration, React + Ant Design.

---

## File Structure

### Backend files to create

- `backend/app/models/agent_run.py`
  - SQLAlchemy `AgentRun` model
- `backend/app/schemas/agent.py`
  - request/response schemas for agent runs
- `backend/app/services/agents/base.py`
  - shared runtime types and step-record helpers
- `backend/app/services/agents/literature_synthesizer.py`
  - built-in agent implementation
- `backend/app/services/agents/reviewer_assistant.py`
  - built-in agent implementation
- `backend/app/services/agent_runtime.py`
  - agent registry, validation, execution orchestration
- `backend/app/api/agents.py`
  - `/api/v1/agents/run` and `/api/v1/agents/runs/{run_id}`
- `backend/alembic/versions/<timestamp>_add_agent_runs.py`
  - migration for `agent_runs` and optional `research_traces.agent_run_id`
- `tests/test_agents_api.py`
  - API tests for request validation, success paths, trace linking, isolation
- `tests/test_agent_runtime.py`
  - direct service tests for step ordering and sanitized failures

### Backend files to modify

- `backend/app/models/__init__.py`
  - export `AgentRun`
- `backend/app/models/trace.py`
  - optional nullable `agent_run_id` foreign key and relationship
- `backend/app/schemas/trace.py`
  - expose `agent_run_id` if needed for UI lookup
- `backend/app/main.py`
  - register `agents_router`
- `backend/app/services/trace_service.py`
  - helper for building trace payloads from agent retrieval results
- `backend/app/services/llm_service.py`
  - helper for non-streaming structured completion if needed
- `tests/test_research_traces.py`
  - add coverage for agent-linked traces

### Frontend files to create

- `frontend/src/types/agent.ts`
  - shared frontend typing for agent requests/responses

### Frontend files to modify

- `frontend/src/pages/Session.tsx`
  - add `Run Agent` entry, modal, result rendering, trace opening
- `frontend/src/locales/en-US.json`
  - add agent UI strings
- `frontend/src/locales/zh-CN.json`
  - add agent UI strings
- `README.md`
  - align product claims with delivered v0 scope

## Task 1: Add `AgentRun` persistence and migration

**Files:**
- Create: `backend/app/models/agent_run.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/trace.py`
- Create: `backend/alembic/versions/<timestamp>_add_agent_runs.py`
- Test: `tests/test_agent_runtime.py`

- [ ] **Step 1: Write the failing model-table registration test**

```python
@pytest.mark.asyncio
async def test_agent_run_table_is_registered(db: AsyncSession):
    result = await db.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    table_names = {name for (name,) in result.all()}

    assert "agent_runs" in Base.metadata.tables.keys()
    assert "agent_runs" in table_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_runtime.py::test_agent_run_table_is_registered -v`
Expected: FAIL because `agent_runs` is not defined yet.

- [ ] **Step 3: Add the SQLAlchemy model**

```python
class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    agent_name: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending", index=True)
    input_json: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    steps_json: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    output_json: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 4: Add the migration**

```python
op.create_table(
    "agent_runs",
    sa.Column("id", sa.String(length=36), primary_key=True),
    sa.Column("session_id", sa.String(length=36), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
    sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    sa.Column("agent_name", sa.String(length=64), nullable=False),
    sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
    sa.Column("input_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    sa.Column("steps_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    sa.Column("output_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    sa.Column("error_message", sa.Text(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
)
```

- [ ] **Step 5: Link traces to agent runs**

```python
agent_run_id: Mapped[str | None] = mapped_column(
    String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True, index=True
)
```

- [ ] **Step 6: Run the targeted tests**

Run: `pytest tests/test_agent_runtime.py::test_agent_run_table_is_registered tests/test_source_extractions.py::test_model_tables_are_registered_and_created -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/agent_run.py backend/app/models/__init__.py backend/app/models/trace.py backend/alembic/versions tests/test_agent_runtime.py tests/test_source_extractions.py
git commit -m "feat: add agent run persistence"
```

## Task 2: Build the backend agent runtime and schemas

**Files:**
- Create: `backend/app/schemas/agent.py`
- Create: `backend/app/services/agents/base.py`
- Create: `backend/app/services/agent_runtime.py`
- Modify: `backend/app/services/trace_service.py`
- Modify: `backend/app/services/llm_service.py`
- Test: `tests/test_agent_runtime.py`

- [ ] **Step 1: Write failing schema validation tests**

```python
def test_literature_synthesizer_requires_two_sources():
    with pytest.raises(ValidationError):
        AgentRunCreateRequest(
            session_id="session-1",
            agent="literature_synthesizer",
            source_ids=["source-1"],
            input={"query": "compare these"}
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_runtime.py::test_literature_synthesizer_requires_two_sources -v`
Expected: FAIL because request schema does not exist yet.

- [ ] **Step 3: Add request/response schemas**

```python
class AgentRunCreateRequest(BaseModel):
    session_id: str
    agent: Literal["literature_synthesizer", "reviewer_assistant"]
    source_ids: list[str] = Field(default_factory=list)
    input: dict[str, Any]

    @model_validator(mode="after")
    def validate_agent_specific_rules(self):
        if self.agent == "literature_synthesizer" and len(self.source_ids) < 2:
            raise ValueError("Literature Synthesizer requires at least 2 sources.")
        return self
```

- [ ] **Step 4: Add step-record helpers and runtime result types**

```python
class AgentStepRecord(TypedDict):
    name: str
    status: str
    summary: str


class AgentExecutionResult(TypedDict):
    output: dict[str, Any]
    steps: list[AgentStepRecord]
    trace_payload: dict[str, Any]
```

- [ ] **Step 5: Add a non-streaming completion helper**

```python
async def complete_llm_response(
    messages: list[dict],
    model: str | None = None,
    api_base: str | None = None,
    api_key: str | None = None,
) -> str:
    chunks: list[str] = []
    async for token in stream_llm_response(messages, model=model, api_base=api_base, api_key=api_key):
        chunks.append(token)
    return "".join(chunks)
```

- [ ] **Step 6: Build the runtime orchestration service**

```python
async def run_agent_definition(
    *,
    agent_name: str,
    source_ids: list[str],
    agent_input: dict[str, Any],
    db: AsyncSession,
    llm_model: str | None,
    llm_api_base: str | None,
    llm_api_key: str | None,
) -> AgentExecutionResult:
    definition = AGENT_REGISTRY[agent_name]
    return await definition.runner(
        source_ids=source_ids,
        agent_input=agent_input,
        db=db,
        llm_model=llm_model,
        llm_api_base=llm_api_base,
        llm_api_key=llm_api_key,
    )
```

- [ ] **Step 7: Run targeted runtime tests**

Run: `pytest tests/test_agent_runtime.py -v`
Expected: PASS for schema validation and helper-level tests.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/agent.py backend/app/services/agents/base.py backend/app/services/agent_runtime.py backend/app/services/trace_service.py backend/app/services/llm_service.py tests/test_agent_runtime.py
git commit -m "feat: add research agent runtime"
```

## Task 3: Implement Literature Synthesizer and Reviewer Assistant

**Files:**
- Create: `backend/app/services/agents/literature_synthesizer.py`
- Create: `backend/app/services/agents/reviewer_assistant.py`
- Modify: `backend/app/services/agent_runtime.py`
- Test: `tests/test_agent_runtime.py`

- [ ] **Step 1: Write a failing Literature Synthesizer happy-path test**

```python
@pytest.mark.asyncio
async def test_literature_synthesizer_records_expected_steps(monkeypatch, db: AsyncSession):
    async def fake_complete(*args, **kwargs):
        return json.dumps({
            "overview": "summary",
            "consensus": ["A"],
            "differences": ["B"],
            "gaps": ["C"],
            "next_questions": ["D"],
        })

    monkeypatch.setattr("app.services.agents.literature_synthesizer.complete_llm_response", fake_complete)

    result = await run_agent_definition(
        agent_name="literature_synthesizer",
        source_ids=["s1", "s2"],
        agent_input={"query": "What do they disagree on?"},
        db=db,
        llm_model=None,
        llm_api_base=None,
        llm_api_key=None,
    )

    assert [step["name"] for step in result["steps"]] == [
        "retrieve", "synthesize", "validate", "format_output"
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_runtime.py::test_literature_synthesizer_records_expected_steps -v`
Expected: FAIL because the agent implementation is missing.

- [ ] **Step 3: Implement Literature Synthesizer**

```python
async def run_literature_synthesizer(...):
    query = agent_input["query"]
    chunks = await retrieve_chunks(query, source_ids, db, mode="rag", top_k=8)
    steps = [_step("retrieve", f"retrieved {len(chunks)} relevant chunks from {len(set(source_ids))} documents")]

    prompt = [
        {"role": "system", "content": LITERATURE_SYNTHESIZER_SYSTEM_PROMPT},
        {"role": "user", "content": build_literature_synthesizer_user_prompt(query, chunks)},
    ]
    raw = await complete_llm_response(prompt, model=llm_model, api_base=llm_api_base, api_key=llm_api_key)
    parsed = _parse_json_response(raw, default_keys=["overview", "consensus", "differences", "gaps", "next_questions"])
    steps.extend([...])
    trace_payload = build_trace_payload(query=query, source_ids=source_ids, retrieved_chunks=chunks)
    return {"output": parsed, "steps": steps, "trace_payload": trace_payload}
```

- [ ] **Step 4: Implement Reviewer Assistant**

```python
async def run_reviewer_assistant(...):
    review_comments = agent_input["review_comments"]
    retrieval_query = agent_input.get("paper_context") or review_comments
    chunks = await retrieve_chunks(retrieval_query, source_ids, db, mode="rag", top_k=8) if source_ids else []
    prompt = [
        {"role": "system", "content": REVIEWER_ASSISTANT_SYSTEM_PROMPT},
        {"role": "user", "content": build_reviewer_assistant_user_prompt(review_comments, agent_input.get("paper_context"), chunks)},
    ]
```

- [ ] **Step 5: Add sanitized parse fallback behavior**

```python
def _parse_json_response(raw: str, default_keys: list[str]) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {"overview": raw.strip()}
    for key in default_keys:
        payload.setdefault(key, [] if key != "overview" else "")
    return payload
```

- [ ] **Step 6: Run targeted tests**

Run: `pytest tests/test_agent_runtime.py -v`
Expected: PASS for both built-in agent implementations and step ordering.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/agents/literature_synthesizer.py backend/app/services/agents/reviewer_assistant.py backend/app/services/agent_runtime.py tests/test_agent_runtime.py
git commit -m "feat: implement built-in research agents"
```

## Task 4: Add agent APIs, persistence, and trace linking

**Files:**
- Create: `backend/app/api/agents.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/schemas/trace.py`
- Test: `tests/test_agents_api.py`
- Test: `tests/test_research_traces.py`

- [ ] **Step 1: Write a failing API smoke test**

```python
@pytest.mark.asyncio
async def test_run_literature_synthesizer_returns_completed_run(
    client: AsyncClient,
    researcher_headers: dict,
    monkeypatch,
):
    monkeypatch.setattr("app.services.agent_runtime.execute_agent_run", fake_execute_agent_run)
    response = await client.post(
        "/api/v1/agents/run",
        json={
            "session_id": "session-id",
            "agent": "literature_synthesizer",
            "source_ids": ["source-1", "source-2"],
            "input": {"query": "compare"},
        },
        headers=researcher_headers,
    )
    assert response.status_code == 201
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agents_api.py::test_run_literature_synthesizer_returns_completed_run -v`
Expected: FAIL because the route does not exist yet.

- [ ] **Step 3: Add the route handlers**

```python
@router.post("/run", response_model=AgentRunResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_run(...):
    session = await _get_session_for_user(body.session_id, user, db)
    run = await execute_agent_run(
        session_id=session.id,
        user_id=user.id,
        agent_name=body.agent,
        source_ids=body.source_ids,
        agent_input=body.input,
        db=db,
    )
    return AgentRunResponse.model_validate(run)
```

- [ ] **Step 4: Persist `AgentRun` and `ResearchTrace` together**

```python
agent_run = AgentRun(
    session_id=session_id,
    user_id=user_id,
    agent_name=agent_name,
    status="running",
    input_json={"source_ids": source_ids, **agent_input},
)
...
trace = ResearchTrace(
    session_id=session_id,
    agent_run_id=agent_run.id,
    user_id=user_id,
    inputs_json=result["trace_payload"]["inputs"],
    retrieval_json=result["trace_payload"]["retrieval"],
    citations_json=result["trace_payload"]["citations"],
    summary_steps_json=result["trace_payload"]["summary_steps"],
)
```

- [ ] **Step 5: Add failure sanitization**

```python
except Exception as exc:
    agent_run.status = "failed"
    agent_run.error_message = "Agent execution failed."
    logger.exception("Agent execution failed: %s", agent_name)
```

- [ ] **Step 6: Run backend API tests**

Run: `pytest tests/test_agents_api.py tests/test_research_traces.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/agents.py backend/app/main.py backend/app/schemas/trace.py tests/test_agents_api.py tests/test_research_traces.py
git commit -m "feat: add research agent APIs"
```

## Task 5: Add minimal session UI for running agents and viewing outputs

**Files:**
- Create: `frontend/src/types/agent.ts`
- Modify: `frontend/src/pages/Session.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`
- Test: manual build check via `npm run build`

- [ ] **Step 1: Add frontend request/response types**

```ts
export interface AgentRunRequest {
  session_id: string;
  agent: 'literature_synthesizer' | 'reviewer_assistant';
  source_ids: string[];
  input: Record<string, unknown>;
}

export interface AgentRunResponse {
  id: string;
  agent_name: string;
  status: string;
  output: Record<string, unknown>;
  steps: Array<{ name: string; status: string; summary: string }>;
  trace: ResearchTraceMeta | null;
}
```

- [ ] **Step 2: Add `Run Agent` entry in the session page**

```tsx
<Button onClick={() => setAgentModalOpen(true)}>
  {t('agent.run')}
</Button>
```

- [ ] **Step 3: Add a simple modal**

```tsx
<Modal open={agentModalOpen} onOk={submitAgentRun} ...>
  <Select value={selectedAgent} ... />
  {selectedAgent === 'literature_synthesizer' ? (
    <Input.TextArea value={agentQuery} ... />
  ) : (
    <Input.TextArea value={reviewComments} ... />
  )}
</Modal>
```

- [ ] **Step 4: Render agent output in the session workspace**

```tsx
const agentMessage: Message = {
  id: `agent-${run.id}`,
  role: 'assistant',
  content: formatAgentOutput(run),
  created_at: new Date().toISOString(),
}
```

- [ ] **Step 5: Link agent trace into the existing trace panel**

```tsx
if (run.trace?.traceId) {
  setTraceByMessageId((prev) => ({
    ...prev,
    [agentMessage.id]: run.trace!,
  }));
}
```

- [ ] **Step 6: Add i18n strings**

```json
"agent.run": "Run Agent",
"agent.literatureSynthesizer": "Literature Synthesizer",
"agent.reviewerAssistant": "Reviewer Assistant",
"agent.query": "Research question",
"agent.reviewComments": "Reviewer comments"
```

- [ ] **Step 7: Run frontend build**

Run: `npm run build`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/src/types/agent.ts frontend/src/pages/Session.tsx frontend/src/locales/en-US.json frontend/src/locales/zh-CN.json
git commit -m "feat: add session UI for research agents"
```

## Task 6: Align extraction/UI copy and README with delivered v0 scope

**Files:**
- Modify: `backend/app/services/extraction_service.py`
- Modify: `frontend/src/pages/Sources.tsx`
- Modify: `README.md`
- Test: `tests/test_source_extractions.py`

- [ ] **Step 1: Write a failing extraction payload test for v0 fields**

```python
def test_build_source_extraction_payload_includes_v0_research_fields():
    payload = build_source_extraction_payload("paper.pdf", "Title\nMethod text. Limitation text.")
    assert "claims" in payload["structured_json"]
    assert "methods" in payload["structured_json"]
    assert "limitations" in payload["structured_json"]
    assert "datasets" in payload["structured_json"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_source_extractions.py::test_build_source_extraction_payload_includes_v0_research_fields -v`
Expected: FAIL

- [ ] **Step 3: Expand extraction payload conservatively**

```python
"structured_json": {
    "title": title,
    "summary": summary,
    "highlights": highlights,
    "claims": [],
    "methods": [],
    "limitations": [],
    "datasets": [],
}
```

- [ ] **Step 4: Replace raw extraction JSON-only presentation with labeled sections**

```tsx
<Descriptions.Item label={t('source.extractionClaims')}>
  {(structured.claims || []).length ? ... : '-'}
</Descriptions.Item>
```

- [ ] **Step 5: Rewrite README feature claims to match implementation**

```md
- Citation-grounded document chat
- Replayable answer traces
- Two built-in research agents for literature synthesis and reviewer response drafting
```

- [ ] **Step 6: Run full fast checks**

Run: `pytest tests/test_source_extractions.py tests/test_agent_runtime.py tests/test_agents_api.py tests/test_research_traces.py -v`
Expected: PASS

Run: `npm run build`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/extraction_service.py frontend/src/pages/Sources.tsx README.md tests/test_source_extractions.py tests/test_agent_runtime.py tests/test_agents_api.py tests/test_research_traces.py
git commit -m "docs: align v0 scope and extraction presentation"
```

## Spec Coverage Check

- `AgentRun` model and persistence: covered by Task 1
- lightweight deterministic runtime: covered by Task 2
- Literature Synthesizer: covered by Task 3
- Reviewer Assistant: covered by Task 3
- agent APIs: covered by Task 4
- trace/citation persistence for runs: covered by Task 4
- minimal UI entry point: covered by Task 5
- future skill-compatible architecture: preserved by Task 2 and Task 3
- extraction/UI/README polish needed for open-source readiness: covered by Task 6

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-07-research-agents-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
