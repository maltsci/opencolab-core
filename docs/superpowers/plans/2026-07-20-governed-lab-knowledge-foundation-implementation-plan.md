# Governed Laboratory Knowledge Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use superpowers:test-driven-development before writing each production change.

**Goal:** Build the authorization-aware laboratory knowledge foundation that makes all permitted asset metadata globally searchable, indexes each ready revision exactly once, and serves project RAG without copying authorization state into the index.

**Architecture:** Transactional `KnowledgeIndexEvent` rows form a durable outbox from catalog, revision, and research-graph mutations. A system ingestion worker maintains metadata, graph, and Qdrant content indexes with stable asset/revision/member/chunk identities. `KnowledgeQueryService` is the only search composition layer: it selects a `lab_global` or `project` scope, applies live policy before retrieval, filters Qdrant by revision identity, reauthorizes returned chunks, and merges safe metadata, graph, and content results.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic V2, Alembic, PostgreSQL/SQLite tests, existing worker runtime, Qdrant, existing embedding gateway, pytest.

---

## Task 1: Persist Durable Knowledge Index Events

**Files:**

- Create: `backend/app/models/knowledge_index_event.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/app/schemas/knowledge_index_event.py`
- Create: `backend/alembic/versions/m3g4h5i6j7k8_add_knowledge_index_events.py`
- Test: `tests/test_knowledge_index_event_model.py`

- [ ] **Step 1: Write failing persistence tests**

Assert event type stability, identifier-only payload validation, unique idempotency keys, retry scheduling, claim ownership, terminal failure, and preservation after asset archival. Assert payloads reject titles, descriptions, extracted text, storage paths, external references, credentials, and policy details.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_knowledge_index_event_model.py -q
```

Expected: FAIL because the event model does not exist.

- [ ] **Step 3: Add the model and migration**

Use these exact event types:

```python
class KnowledgeIndexEventType(StrEnum):
    CATALOG_PUBLISHED = "catalog_published"
    CATALOG_UPDATED = "catalog_updated"
    REVISION_READY = "revision_ready"
    CURRENT_REVISION_CHANGED = "current_revision_changed"
    CLASSIFICATION_CHANGED = "classification_changed"
    CATALOG_WITHDRAWN = "catalog_withdrawn"
    ASSET_ARCHIVED = "asset_archived"
    RELATION_CHANGED = "relation_changed"
```

Implement `KnowledgeIndexEvent` with `id`, `event_type`, nullable `research_asset_id`, `asset_revision_id`, `asset_content_member_id`, and `research_object_relation_id`, plus `idempotency_key`, `status`, `attempt_count`, `available_at`, `claimed_at`, `claimed_by`, `processed_at`, `last_error_code`, and timestamps. Status values are `pending`, `processing`, `processed`, and `failed`.

The migration creates indexes on `(status, available_at)`, each foreign key, and a unique constraint on `idempotency_key`. Foreign keys use `SET NULL` where event history must survive retirement.

Use:

```python
revision = "m3g4h5i6j7k8"
down_revision = "l2f3g4h5i6j7"
```

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_knowledge_index_event_model.py -q
git add backend/app/models/knowledge_index_event.py backend/app/models/__init__.py backend/app/schemas/knowledge_index_event.py backend/alembic/versions/m3g4h5i6j7k8_add_knowledge_index_events.py tests/test_knowledge_index_event_model.py
git commit -m "feat: add knowledge index event outbox"
```

## Task 2: Emit Transactional Catalog, Revision, and Graph Events

**Files:**

- Create: `backend/app/services/knowledge_index_event_service.py`
- Modify: `backend/app/services/research_asset_service.py`
- Modify: `backend/app/services/asset_revision_service.py`
- Modify: `backend/app/services/relation_service.py`
- Test: `tests/test_knowledge_index_event_service.py`

- [ ] **Step 1: Write failing transactional tests**

Cover event creation in the same transaction as catalog publish/update/withdraw/archive, revision seal/current change, classification change, and relation create/update/delete. Rollback must remove both mutation and event. Repeating the same mutation command must not duplicate an event.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_knowledge_index_event_service.py -q
```

- [ ] **Step 3: Implement the event writer**

Required public signature:

```python
async def append_knowledge_index_event(
    db: AsyncSession,
    *,
    event_type: KnowledgeIndexEventType,
    idempotency_key: str,
    asset_id: UUID | None = None,
    revision_id: UUID | None = None,
    member_id: UUID | None = None,
    relation_id: UUID | None = None,
) -> KnowledgeIndexEvent
```

Callers build deterministic keys from command identity and resulting version, never from protected content. The service flushes but does not commit; the caller owns the transaction. Do not emit events for grants, requests, approvals, revocations, expiry, project links, or user membership changes because those states are evaluated live.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_knowledge_index_event_service.py tests/test_asset_revisions.py -q
git add backend/app/services/knowledge_index_event_service.py backend/app/services/research_asset_service.py backend/app/services/asset_revision_service.py backend/app/services/relation_service.py tests/test_knowledge_index_event_service.py
git commit -m "feat: emit transactional knowledge events"
```

## Task 3: Index Ready Revisions Under a System Ingestion Identity

**Files:**

- Create: `backend/app/services/knowledge_index_service.py`
- Modify: `backend/app/services/vector_store.py`
- Modify: `backend/app/worker/main.py`
- Test: `tests/test_knowledge_index_service.py`
- Modify: `tests/test_worker_startup.py`

- [ ] **Step 1: Write failing indexing tests**

Assert:

- every ready parseable revision is embedded once, independent of user grants;
- catalog-only members never produce vectors;
- vectors contain only `research_asset_id`, `asset_revision_id`, `asset_content_member_id`, `chunk_id`, format, and non-sensitive retrieval fields;
- no user, role, project, grant, classification, policy, or approval data enters vector payloads;
- retries upsert stable point IDs and never duplicate chunks;
- current-revision changes do not delete older revision vectors;
- withdrawn or archived assets are excluded by the query layer and may be removed asynchronously;
- system ingestion access is audited and cannot be used as a human or Agent authorization bypass.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_knowledge_index_service.py tests/test_worker_startup.py -q
```

- [ ] **Step 3: Implement idempotent event processing**

Required contracts:

```python
async def process_knowledge_event(
    db: AsyncSession,
    *,
    event: KnowledgeIndexEvent,
    worker_id: str,
) -> None

async def claim_knowledge_events(
    db: AsyncSession,
    *,
    worker_id: str,
    batch_size: int,
    now: datetime,
) -> tuple[KnowledgeIndexEvent, ...]
```

Claim rows using `FOR UPDATE SKIP LOCKED` on PostgreSQL and a transaction-safe SQLite fallback for tests. Re-read authoritative database state during processing. Generate each vector point ID deterministically from revision/member/chunk identity. Retry with bounded exponential backoff and a stable safe error code; never store exception text that may contain content.

The system ingestion actor may read managed extraction only for indexing and must use a separate gateway capability path that is unavailable to human and Agent callers. Emit an immutable audit event with asset/revision/member IDs and no content.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_knowledge_index_service.py tests/test_worker_startup.py -q
git add backend/app/services/knowledge_index_service.py backend/app/services/vector_store.py backend/app/worker/main.py tests/test_knowledge_index_service.py tests/test_worker_startup.py
git commit -m "feat: index governed asset revisions"
```

## Task 4: Build the Authorization-Aware Knowledge Query Service

**Files:**

- Create: `backend/app/schemas/knowledge_query.py`
- Create: `backend/app/services/knowledge_query_service.py`
- Test: `tests/test_knowledge_query_service.py`

- [ ] **Step 1: Write the failing scope and disclosure matrix**

Cover:

| Scope | Metadata | Protected content |
|---|---|---|
| `lab_global` without project | Authorized L0–L3 metadata; L4 only by explicit discovery policy | L0/L1 only when explicit baseline permits; never L2–L4 |
| `project` | Same metadata plus project-link state | Only linked, exact revisions with live `content:use_in_agent` |

Also assert:

- L2–L4 project content requires active membership, purpose, bounded authorization, revision grant, and live agreement state;
- metadata-only results can say that supporting internal data exists without disclosing protected fields;
- unauthorized or hidden L4 results never influence counts, facets, snippets, graph expansion, timing-visible follow-up work, or suggestions;
- returned chunks are reauthorized after Qdrant retrieval;
- revocation and expiry take effect on the next query without re-indexing.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_knowledge_query_service.py -q
```

- [ ] **Step 3: Define query contracts**

```python
class KnowledgeQueryScope(StrEnum):
    LAB_GLOBAL = "lab_global"
    PROJECT = "project"


class KnowledgeResultState(StrEnum):
    CONTENT_AVAILABLE = "content_available"
    METADATA_ONLY = "metadata_only"
    REQUESTABLE = "requestable"
    APPROVAL_PENDING = "approval_pending"
    NOT_REQUESTABLE = "not_requestable"
```

Required public signature:

```python
async def search_knowledge(
    db: AsyncSession,
    *,
    user: User,
    query: str,
    scope: KnowledgeQueryScope,
    project_id: UUID | None,
    purpose: str | None,
    limit: int,
    cursor: str | None,
) -> KnowledgeSearchPage
```

The service executes this order:

1. Validate user and optional project context.
2. Query safe catalog metadata and research-graph candidates.
3. Remove hidden L4 candidates before facets, counts, or graph traversal.
4. Resolve live metadata and content decisions for candidate revision identities.
5. In `project` scope, intersect with active `ProjectAssetLink` revision eligibility.
6. Query Qdrant only with the resulting authorized revision IDs.
7. Reauthorize every returned chunk and drop denied results.
8. Merge metadata-only, graph, and content results with stable cursor pagination.

Qdrant is a relevance index, never an authorization source. Do not cache allow decisions beyond one service call.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_knowledge_query_service.py -q
git add backend/app/schemas/knowledge_query.py backend/app/services/knowledge_query_service.py tests/test_knowledge_query_service.py
git commit -m "feat: add governed knowledge queries"
```

## Task 5: Expose Search and Index Operations APIs

**Files:**

- Create: `backend/app/api/knowledge.py`
- Create: `backend/app/api/knowledge_admin.py`
- Modify: `backend/app/main.py`
- Test: `tests/test_knowledge_api.py`

- [ ] **Step 1: Write failing API tests**

Test `GET /api/v1/knowledge/search` with `scope`, `project_id`, `q`, `limit`, and `cursor`. Validate that `project_id` is optional for `lab_global`, required for project protected-content retrieval, and never accepted as an implicit grant.

Test admin-only:

```text
GET  /api/v1/admin/knowledge-index/status
POST /api/v1/admin/knowledge-index/events/{event_id}/retry
```

Retry requires a terminal failed event, resets only scheduling fields, and writes an audit event. Ordinary users cannot inspect event errors or retry work.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_knowledge_api.py -q
```

- [ ] **Step 3: Implement thin routes**

Routes validate input and delegate to `KnowledgeQueryService` or `KnowledgeIndexService`. Search responses include safe asset metadata, category/subtype, current or matched revision identity, safe member formats, access state, request eligibility, relation summaries, and authorized citations. They never contain Source IDs, storage identity, protected metadata, raw policy rules, approver identities, or hidden-result totals.

Keep generative synthesis out of V1 `/knowledge/search`. Reserve `/api/v1/knowledge/query` for a later answer-generation phase that will consume the same query service.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_knowledge_api.py -q
git add backend/app/api/knowledge.py backend/app/api/knowledge_admin.py backend/app/main.py tests/test_knowledge_api.py
git commit -m "feat: expose governed knowledge search"
```

## Task 6: Backfill and Reconcile Existing Knowledge Indexes

**Files:**

- Create: `backend/app/services/knowledge_index_backfill.py`
- Create: `backend/app/cli/knowledge_index.py`
- Test: `tests/test_knowledge_index_backfill.py`

- [ ] **Step 1: Write failing reconciliation tests**

Cover ready revisions with missing vectors, duplicated legacy vectors, orphan vectors, catalog-only members with vectors, and processed events whose vectors are absent. Dry-run returns counts without mutation. Re-running apply mode is idempotent.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_knowledge_index_backfill.py -q
```

- [ ] **Step 3: Implement dry-run-first reconciliation**

Expose:

```python
@dataclass(frozen=True)
class KnowledgeIndexBackfillReport:
    revisions_scanned: int
    events_created: int
    legacy_points_removed: int
    orphan_points_removed: int
    unmatched_revision_ids: tuple[UUID, ...]


async def reconcile_knowledge_index(
    db: AsyncSession,
    *,
    dry_run: bool,
    batch_size: int = 500,
) -> KnowledgeIndexBackfillReport
```

Create deterministic `revision_ready` events for ready parseable revisions lacking a processed identity. Remove legacy or orphan points only in apply mode and only when their replacement identity is known. Unknown mappings remain in the report for administrator review.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_knowledge_index_backfill.py -q
git add backend/app/services/knowledge_index_backfill.py backend/app/cli/knowledge_index.py tests/test_knowledge_index_backfill.py
git commit -m "feat: reconcile governed knowledge index"
```

## Task 7: Phase Verification

- [ ] **Step 1: Run focused knowledge tests**

```bash
backend/.venv/bin/python -m pytest tests/test_knowledge_index_event_model.py tests/test_knowledge_index_event_service.py tests/test_knowledge_index_service.py tests/test_knowledge_query_service.py tests/test_knowledge_api.py tests/test_knowledge_index_backfill.py -q
```

- [ ] **Step 2: Run full checks**

```bash
backend/.venv/bin/python -m pytest -q
git diff --check
pre-commit run
```

- [ ] **Step 3: Verify authorization changes require no re-index**

In a disposable environment, index one L3 revision once. Verify metadata-only global search, grant project use, revoke it, expire a second grant, and change project membership. Confirm the vector point IDs and counts never change while content eligibility changes immediately. Confirm an unauthorized L4 asset does not affect results or facets.

- [ ] **Step 4: Create a checkpoint commit only if verification changed files**

```bash
git status --short
```

If verification requires a tracked fix, return to the task that owns that file, repeat its failing-test and implementation steps, and use that task's exact commit command. Do not create a catch-all verification commit.

Expected: all checks pass and no verification-only edits remain uncommitted.
