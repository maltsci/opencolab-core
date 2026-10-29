# OpenColab V0 Iteration 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first visible LRAR slice: structured extraction for uploaded sources, a minimal research trace model, and frontend surfaces that let users inspect extracted data and citation/trace placeholders.

**Architecture:** Extend the existing source ingestion and chat pipeline instead of replacing it. Store extraction and trace data in PostgreSQL, reuse the current worker for post-processing, and expose the results through the existing `Sources` and `Session` pages so Docker rebuilds yield immediate UI feedback.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic v2, React, Vite, Ant Design, pytest

---

## File Structure

### Backend files

- Create: `backend/app/models/research_object.py`
- Create: `backend/app/models/trace.py`
- Create: `backend/app/schemas/extraction.py`
- Create: `backend/app/schemas/trace.py`
- Create: `backend/app/services/extraction_service.py`
- Create: `backend/app/services/citation_service.py`
- Create: `backend/app/services/trace_service.py`
- Create: `backend/app/api/research_threads.py`
- Create: a new Alembic revision file under `backend/alembic/versions/` for extraction and trace tables
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/source.py`
- Modify: `backend/app/schemas/source.py`
- Modify: `backend/app/api/sources.py`
- Modify: `backend/app/api/websocket.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/worker/main.py`

### Frontend files

- Modify: `frontend/src/hooks/useWebSocket.ts`
- Modify: `frontend/src/pages/Sources.tsx`
- Modify: `frontend/src/pages/Session.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`

### Tests

- Create: `tests/test_source_extractions.py`
- Create: `tests/test_research_traces.py`
- Modify: `tests/conftest.py` if model imports need fixture updates

## Task 1: Add Extraction, ResearchObject, and Trace Models

**Files:**
- Create: `backend/app/models/research_object.py`
- Create: `backend/app/models/trace.py`
- Modify: `backend/app/models/source.py`
- Modify: `backend/app/models/__init__.py`
- Create: a new Alembic revision file under `backend/alembic/versions/`
- Test: `tests/test_source_extractions.py`

- [ ] **Step 1: Write the failing model serialization test**

```python
from app.models.source import Source
from app.schemas.extraction import SourceExtractionResponse


def test_source_extraction_response_round_trip():
    payload = {
        "id": "ext-1",
        "source_id": "src-1",
        "status": "ready",
        "document_type": "paper",
        "structured_json": {
            "claims": [{"statement": "A", "evidence": "B", "confidence": 0.8}],
            "methods": ["cnn"],
            "limitations": ["small dataset"],
        },
    }

    result = SourceExtractionResponse.model_validate(payload)

    assert result.source_id == "src-1"
    assert result.structured_json["methods"] == ["cnn"]
    assert result.structured_json["claims"][0]["statement"] == "A"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_source_extractions.py::test_source_extraction_response_round_trip -v
```

Expected: FAIL with `ModuleNotFoundError` or missing `SourceExtractionResponse`.

- [ ] **Step 3: Add SQLAlchemy models and relationships**

```python
# backend/app/models/research_object.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ResearchObject(Base):
    __tablename__ = "research_objects"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    type: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ResearchObjectRelation(Base):
    __tablename__ = "research_object_relations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    source_object_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_objects.id", ondelete="CASCADE"), index=True
    )
    target_object_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_objects.id", ondelete="CASCADE"), index=True
    )
    relation_type: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    source_object: Mapped["ResearchObject"] = relationship(
        foreign_keys=[source_object_id]
    )
    target_object: Mapped["ResearchObject"] = relationship(
        foreign_keys=[target_object_id]
    )
```

```python
# backend/app/models/trace.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SourceExtraction(Base):
    __tablename__ = "source_extractions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="CASCADE"), unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    document_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    schema_version: Mapped[str] = mapped_column(String(20), default="v1", server_default="v1")
    structured_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    source: Mapped["Source"] = relationship(back_populates="extraction")


class ResearchTrace(Base):
    __tablename__ = "research_traces"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    inputs_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    retrieval_json: Mapped[list] = mapped_column(JSONB, default=list)
    citations_json: Mapped[list] = mapped_column(JSONB, default=list)
    summary_steps_json: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

```python
# backend/app/models/source.py
from app.models.trace import SourceExtraction

class Source(Base):
    ...
    extraction: Mapped["SourceExtraction | None"] = relationship(
        back_populates="source", uselist=False, cascade="all, delete-orphan", passive_deletes=True
    )
```

- [ ] **Step 4: Add Pydantic schemas**

```python
# backend/app/schemas/extraction.py
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SourceExtractionResponse(BaseModel):
    id: str
    source_id: str
    status: str
    document_type: str | None = None
    schema_version: str = "v1"
    structured_json: dict[str, Any]
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
```

```python
# backend/app/schemas/trace.py
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ResearchTraceResponse(BaseModel):
    id: str
    session_id: str
    message_id: str | None = None
    inputs: dict[str, Any]
    retrieval: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    summary_steps: list[str]
    created_at: datetime | None = None
```

- [ ] **Step 5: Generate and fill the Alembic migration**

Run:

```bash
cd backend && PYTHONPATH=. alembic revision -m "add extractions and traces"
```

Expected: a new file appears under `backend/alembic/versions/`.

```python
def upgrade() -> None:
    op.create_table(
        "source_extractions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("document_type", sa.String(length=32), nullable=True),
        sa.Column("schema_version", sa.String(length=20), server_default="v1", nullable=False),
        sa.Column("structured_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id"),
    )

    op.create_table(
        "research_traces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("inputs_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("retrieval_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("citations_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("summary_steps_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
```

- [ ] **Step 6: Run targeted tests**

Run:

```bash
pytest tests/test_source_extractions.py::test_source_extraction_response_round_trip -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/models backend/app/schemas backend/alembic tests/test_source_extractions.py
git commit -m "feat: add extraction and trace models"
```

## Task 2: Hook Structured Extraction into the Worker and Source API

**Files:**
- Create: `backend/app/services/extraction_service.py`
- Modify: `backend/app/worker/main.py`
- Modify: `backend/app/api/sources.py`
- Modify: `backend/app/schemas/source.py`
- Test: `tests/test_source_extractions.py`

- [ ] **Step 1: Write the failing extraction endpoint test**

```python
def test_get_source_extraction_returns_structured_payload(client, auth_headers, source, db_session):
    extraction = SourceExtraction(
        source_id=source.id,
        status="ready",
        document_type="paper",
        structured_json={"methods": ["cnn"], "limitations": ["small dataset"]},
    )
    db_session.add(extraction)
    db_session.commit()

    response = client.get(f"/api/v1/sources/{source.id}/extraction", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["structured_json"]["methods"] == ["cnn"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_source_extractions.py::test_get_source_extraction_returns_structured_payload -v
```

Expected: FAIL with `404` or missing route.

- [ ] **Step 3: Implement extraction service**

```python
# backend/app/services/extraction_service.py
from collections.abc import Sequence


def build_extraction_payload(source_name: str, chunks: Sequence[str]) -> dict:
    joined = "\n\n".join(chunks[:8]).strip()
    methods = []
    limitations = []
    claims = []

    for line in joined.splitlines():
        lowered = line.lower()
        if "method" in lowered and len(methods) < 5:
            methods.append(line[:240])
        if ("limitation" in lowered or "future work" in lowered) and len(limitations) < 5:
            limitations.append(line[:240])
        if any(token in lowered for token in ("improves", "increase", "decrease", "outperform")) and len(claims) < 5:
            claims.append(
                {
                    "statement": line[:240],
                    "evidence": line[:240],
                    "confidence": 0.4,
                }
            )

    return {
        "title": source_name,
        "claims": claims,
        "methods": methods,
        "limitations": limitations,
    }
```

- [ ] **Step 4: Save extraction during worker processing**

```python
# backend/app/worker/main.py
from app.models.trace import SourceExtraction
from app.services.extraction_service import build_extraction_payload

...
        extraction_payload = build_extraction_payload(source_name, chunks_text)

        async with async_session_factory() as db:
            result = await db.execute(select(Source).where(Source.id == source_id))
            source = result.scalar_one()
            if source.extraction is None:
                source.extraction = SourceExtraction(
                    status="ready",
                    document_type="paper",
                    structured_json=extraction_payload,
                )
            else:
                source.extraction.status = "ready"
                source.extraction.document_type = "paper"
                source.extraction.structured_json = extraction_payload
                source.extraction.error_message = None
            await db.commit()
```

- [ ] **Step 5: Expose extraction from the source API**

```python
# backend/app/api/sources.py
from app.models.trace import SourceExtraction
from app.schemas.extraction import SourceExtractionResponse


@router.get("/sources/{source_id}/extraction", response_model=SourceExtractionResponse)
async def get_source_extraction(
    source_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await can_user_access_source(user.id, source_id, db):
        raise HTTPException(status_code=404, detail="Source not found")

    result = await db.execute(
        select(SourceExtraction).where(SourceExtraction.source_id == source_id)
    )
    extraction = result.scalar_one_or_none()
    if extraction is None:
        raise HTTPException(status_code=404, detail="Extraction not found")
    return SourceExtractionResponse.model_validate(extraction)
```

- [ ] **Step 6: Add extraction status onto `SourceResponse`**

```python
class SourceResponse(BaseModel):
    ...
    extraction_status: str | None = None
```

- [ ] **Step 7: Run targeted tests**

Run:

```bash
pytest tests/test_source_extractions.py -v
```

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/sources.py backend/app/services/extraction_service.py backend/app/worker/main.py backend/app/schemas/source.py tests/test_source_extractions.py
git commit -m "feat: expose structured source extractions"
```

## Task 3: Add Minimal Citation and Research Trace Persistence to Chat

**Files:**
- Create: `backend/app/services/citation_service.py`
- Create: `backend/app/services/trace_service.py`
- Create: `backend/app/api/research_threads.py`
- Modify: `backend/app/api/websocket.py`
- Modify: `backend/app/main.py`
- Test: `tests/test_research_traces.py`

- [ ] **Step 1: Write the failing trace payload test**

```python
def test_trace_payload_only_contains_v0_fields():
    payload = build_trace_payload(
        query="What does this paper claim?",
        source_ids=["src-1"],
        retrieved_chunks=[{"source_id": "src-1", "chunk_id": "c1", "score": 0.9, "text": "chunk"}],
    )

    assert set(payload.keys()) == {"inputs", "retrieval", "citations", "summary_steps"}
    assert payload["inputs"]["query"] == "What does this paper claim?"
    assert payload["retrieval"][0]["chunk_id"] == "c1"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_research_traces.py::test_trace_payload_only_contains_v0_fields -v
```

Expected: FAIL because `build_trace_payload` does not exist.

- [ ] **Step 3: Implement citation and trace services**

```python
# backend/app/services/citation_service.py
def build_citations(chunks: list[dict]) -> list[dict]:
    citations = []
    for chunk in chunks:
        citations.append(
            {
                "source_id": chunk["source_id"],
                "chunk_id": chunk["chunk_id"],
                "snippet": chunk["text"][:280],
                "score": chunk.get("score"),
            }
        )
    return citations
```

```python
# backend/app/services/trace_service.py
from app.models.trace import ResearchTrace


def build_trace_payload(query: str, source_ids: list[str], retrieved_chunks: list[dict]) -> dict:
    citations = build_citations(retrieved_chunks)
    return {
        "inputs": {"query": query, "source_ids": source_ids},
        "retrieval": [
            {
                "source_id": chunk["source_id"],
                "chunk_id": chunk["chunk_id"],
                "score": chunk.get("score"),
            }
            for chunk in retrieved_chunks
        ],
        "citations": citations,
        "summary_steps": [
            f"selected {len(source_ids)} documents",
            f"retrieved {len(retrieved_chunks)} relevant chunks",
            f"generated answer with {len(citations)} citations",
        ],
    }
```

- [ ] **Step 4: Save traces and emit citations at WebSocket completion**

```python
# backend/app/api/websocket.py
trace_payload = build_trace_payload(content, expanded_source_ids, chunks)

trace = ResearchTrace(
    session_id=session_id,
    message_id=assistant_msg.id,
    user_id=user_id,
    inputs_json=trace_payload["inputs"],
    retrieval_json=trace_payload["retrieval"],
    citations_json=trace_payload["citations"],
    summary_steps_json=trace_payload["summary_steps"],
)
db.add(trace)
await db.commit()
await db.refresh(trace)

await websocket.send_json(
    {
        "type": "done",
        "message_id": assistant_msg.id,
        "trace_id": trace.id,
        "citations": trace_payload["citations"],
        "summary_steps": trace_payload["summary_steps"],
    }
)
```

- [ ] **Step 5: Add read API for traces**

```python
# backend/app/api/research_threads.py
router = APIRouter(prefix="/sessions", tags=["research-threads"])


@router.get("/{session_id}/trace", response_model=list[ResearchTraceResponse])
async def list_session_traces(...):
    result = await db.execute(
        select(ResearchTrace)
        .where(ResearchTrace.session_id == session_id)
        .order_by(ResearchTrace.created_at.desc())
    )
    return [
        ResearchTraceResponse(
            id=trace.id,
            session_id=trace.session_id,
            message_id=trace.message_id,
            inputs=trace.inputs_json,
            retrieval=trace.retrieval_json,
            citations=trace.citations_json,
            summary_steps=trace.summary_steps_json,
            created_at=trace.created_at,
        )
        for trace in result.scalars().all()
    ]
```

- [ ] **Step 6: Register the new router**

```python
# backend/app/main.py
from app.api.research_threads import router as research_threads_router

...
app.include_router(research_threads_router, prefix=api)
```

- [ ] **Step 7: Run targeted tests**

Run:

```bash
pytest tests/test_research_traces.py -v
```

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/services backend/app/api/research_threads.py backend/app/api/websocket.py backend/app/main.py tests/test_research_traces.py
git commit -m "feat: persist chat citations and traces"
```

## Task 4: Surface Extraction and Trace Data in the Frontend

**Files:**
- Modify: `frontend/src/hooks/useWebSocket.ts`
- Modify: `frontend/src/pages/Sources.tsx`
- Modify: `frontend/src/pages/Session.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`

- [ ] **Step 1: Add frontend state types for extraction and trace**

```ts
interface SourceExtraction {
  id: string;
  source_id: string;
  status: string;
  document_type: string | null;
  structured_json: {
    claims?: Array<{ statement: string; evidence?: string; confidence?: number }>;
    methods?: string[];
    limitations?: string[];
  };
}

interface TraceSummary {
  trace_id?: string;
  citations: Array<{ source_id: string; chunk_id?: string; snippet?: string; score?: number }>;
  summary_steps: string[];
}
```

- [ ] **Step 2: Extend the WebSocket hook to store done-event metadata**

```ts
interface WSMessage {
  type: 'token' | 'done' | 'error' | 'title_updated';
  content?: string;
  message_id?: string;
  trace_id?: string;
  citations?: Array<{ source_id: string; chunk_id?: string; snippet?: string; score?: number }>;
  summary_steps?: string[];
  message?: string;
  title?: string;
}

const [lastTrace, setLastTrace] = useState<TraceSummary | null>(null);

...
} else if (data.type === 'done') {
  setLastTrace({
    trace_id: data.trace_id,
    citations: data.citations || [],
    summary_steps: data.summary_steps || [],
  });
  setIsStreaming(false);
}
```

- [ ] **Step 3: Show extraction details in `Sources.tsx`**

```tsx
const [selectedExtraction, setSelectedExtraction] = useState<SourceExtraction | null>(null);

const openExtraction = async (sourceId: string) => {
  const { data } = await apiClient.get(`/sources/${sourceId}/extraction`);
  setSelectedExtraction(data);
};

<Button size="small" onClick={() => openExtraction(record.id)}>
  {t('source.viewExtraction')}
</Button>

<Modal
  title={t('source.extractionTitle')}
  open={!!selectedExtraction}
  onCancel={() => setSelectedExtraction(null)}
  footer={null}
>
  <List
    header={t('source.methods')}
    dataSource={selectedExtraction?.structured_json.methods || []}
    renderItem={(item) => <List.Item>{item}</List.Item>}
  />
</Modal>
```

- [ ] **Step 4: Show trace and citation cards in `Session.tsx`**

```tsx
const [latestTrace, setLatestTrace] = useState<TraceSummary | null>(null);
const { ..., lastTrace } = useWebSocket(sessionId);

useEffect(() => {
  if (lastTrace) {
    setLatestTrace(lastTrace);
  }
}, [lastTrace]);

<Sider width={320} theme="light">
  <Card title={t('session.traceTitle')} size="small">
    <List
      size="small"
      dataSource={latestTrace?.summary_steps || []}
      renderItem={(item) => <List.Item>{item}</List.Item>}
    />
  </Card>
  <Card title={t('session.citationsTitle')} size="small" style={{ marginTop: 12 }}>
    <List
      size="small"
      dataSource={latestTrace?.citations || []}
      renderItem={(item) => <List.Item>{item.snippet || item.chunk_id}</List.Item>}
    />
  </Card>
</Sider>
```

- [ ] **Step 5: Add i18n labels**

```json
{
  "source.viewExtraction": "View extraction",
  "source.extractionTitle": "Structured extraction",
  "source.methods": "Methods",
  "session.traceTitle": "Research trace",
  "session.citationsTitle": "Citations"
}
```

- [ ] **Step 6: Run frontend verification**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS with a production build in `dist/`.

- [ ] **Step 7: Rebuild Docker services and smoke test**

Run:

```bash
docker compose up -d --build frontend api worker
```

Expected:

- `http://localhost:8430` loads
- `Sources` page shows a button or modal for structured extraction
- `Session` page shows trace and citation side panels after a response

- [ ] **Step 8: Commit**

```bash
git add frontend/src frontend/src/locales
git commit -m "feat: surface extraction and trace data"
```

## Self-Review

### Spec coverage

- Structured extraction: covered in Tasks 1-2.
- Research trace with `inputs / retrieval / citations / summary_steps`: covered in Task 3.
- Visible UI changes in sources and sessions: covered in Task 4.
- ResearchObject foundation: covered in Task 1 model setup.

### Placeholder scan

- No `TBD`, `TODO`, or deferred implementation markers remain inside executable steps.
- The Docker rebuild step is explicit because this compose setup does not hot-reload source code into containers.

### Type consistency

- `SourceExtractionResponse` and `ResearchTraceResponse` field names match the v0 spec.
- `ResearchTrace` persists `*_json` fields; API responses map them back to `inputs`, `retrieval`, `citations`, and `summary_steps`.
- Frontend uses `trace_id`, `citations`, and `summary_steps`, which match the WebSocket `done` event payload in Task 3.
