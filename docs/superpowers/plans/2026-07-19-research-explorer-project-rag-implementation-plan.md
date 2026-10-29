# Research Explorer and Project RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use superpowers:test-driven-development before writing each production change.

**Goal:** Provide laboratory-wide metadata search, version/member-aware catalog UI, access request and approval surfaces, and policy-safe project RAG that can cite only currently authorized asset revisions.

**Architecture:** The Explorer and project RAG both consume the Phase 4 `KnowledgeQueryService`; neither implements an independent search or authorization path. Global scope returns safe metadata without a project, while project scope intersects links and exact-revision authorization before Qdrant retrieval and reauthorizes every returned chunk. Agent responses may mention inaccessible discoverable evidence only as metadata, never as content.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL full-text-compatible search with SQLite test fallback, Qdrant, LangGraph, WebSocket, React, TypeScript, Ant Design, React Query, i18next, pytest.

---

## Task 1: Define Safe Catalog and Access Summary Schemas

**Files:**

- Modify: `backend/app/schemas/research_asset.py`
- Create: `backend/app/schemas/research_catalog.py`
- Test: `tests/test_research_catalog_schemas.py`

- [ ] **Step 1: Write failing disclosure tests**

Construct an asset with sensitive values in `protected_metadata_json`, locator ciphertext, local path, extraction text, and policy conditions. Assert the catalog schema contains none of them.

The list result must contain:

- ID, title, safe description, asset category and subtype;
- classification, owning group display name;
- catalog metadata;
- current or matched revision number, processing state, and safe member-format summary;
- access state and allowed capabilities;
- request eligibility and approval hint;
- created and updated timestamps.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_research_catalog_schemas.py -q
```

Expected: FAIL because catalog schemas do not exist.

- [ ] **Step 3: Add exact response types**

```python
class AssetAccessSummary(BaseModel):
    state: Literal[
        "content_available",
        "metadata_only",
        "requestable",
        "approval_pending",
        "not_requestable",
    ]
    allowed_capabilities: list[Capability]
    requestable_capabilities: list[Capability]
    approval_hint: Literal[
        "asset_owner",
        "asset_owner_or_pi",
        "asset_owner_and_pi",
    ] | None = None
    expires_at: datetime | None = None


class ResearchCatalogItem(BaseModel):
    id: UUID
    title: str
    description: str | None
    asset_category: AssetCategory
    asset_subtype: str | None
    classification: AssetClassification
    owning_group: ResearchGroupSummary
    catalog_metadata_json: dict[str, JsonValue]
    revision_id: UUID | None
    revision_number: int | None
    processing_state: AssetRevisionState | None
    member_formats: list[str]
    linked_to_project: bool | None
    access: AssetAccessSummary
    created_at: datetime
    updated_at: datetime
```

Do not include `source_id`, `research_object_id`, `member_id`, `protected_metadata_json`, storage identifiers, external references, approval identities, or policy conditions in list results.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_research_catalog_schemas.py -q
git add backend/app/schemas/research_asset.py backend/app/schemas/research_catalog.py tests/test_research_catalog_schemas.py
git commit -m "feat: define safe research catalog responses"
```

## Task 2: Adapt Explorer Search to KnowledgeQueryService

**Files:**

- Create: `backend/app/services/research_catalog_service.py`
- Modify: `backend/app/services/knowledge_query_service.py`
- Test: `tests/test_research_catalog_service.py`

- [ ] **Step 1: Write failing search tests**

Cover:

- Search by title, safe description, category/subtype, member format, and allowlisted catalog metadata values.
- Results across multiple research groups.
- Restricted asset discovery without content access.
- An asset outside the caller's `metadata:view` baseline or explicit policy is absent.
- Filters for group, project, classification, category, subtype, member format, revision state, and access state.
- Cursor pagination is stable with duplicate timestamps.
- Search never loads or matches protected metadata or extracted content.
- Draft, withdrawn, archived, and unauthorized L4 catalog behavior follows the approved design.
- Empty query returns recent discoverable assets.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_research_catalog_service.py -q
```

- [ ] **Step 3: Implement the query contract**

```python
@dataclass(frozen=True)
class ResearchCatalogQuery:
    text: str | None
    group_ids: frozenset[UUID]
    scope: KnowledgeQueryScope
    project_id: UUID | None
    classifications: frozenset[AssetClassification]
    asset_categories: frozenset[AssetCategory]
    asset_subtypes: frozenset[str]
    member_formats: frozenset[str]
    revision_states: frozenset[AssetRevisionState]
    access_states: frozenset[str]
    cursor: str | None
    limit: int


@dataclass(frozen=True)
class ResearchCatalogPage:
    items: tuple[ResearchCatalogItem, ...]
    next_cursor: str | None
```

Required public signature: `async def search_research_catalog(db: AsyncSession, *, user: User, query: ResearchCatalogQuery) -> ResearchCatalogPage`.

Implementation rules:

1. Translate Explorer filters into the Phase 4 knowledge-query contract.
2. Use `lab_global` when the caller has no selected project; never require a project for metadata discovery.
3. Use `project` only when the caller explicitly selects a project.
4. Map `KnowledgeSearchPage` to Explorer response schemas without loading content or reimplementing policy evaluation.
5. Preserve the signed cursor from `KnowledgeQueryService`.

This service is an adapter only. It must not query Qdrant, policy, grants, protected metadata, or extracted chunks directly.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_research_catalog_service.py -q
git add backend/app/services/research_catalog_service.py backend/app/services/knowledge_query_service.py tests/test_research_catalog_service.py
git commit -m "feat: search governed research catalog"
```

## Task 3: Add Research Explorer APIs

**Files:**

- Create: `backend/app/api/research_catalog.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/research_assets.py`
- Test: `tests/test_research_catalog_api.py`

- [ ] **Step 1: Write failing API tests**

Test:

```text
GET /api/v1/knowledge/search
GET /api/v1/research-assets/{asset_id}/catalog
GET /api/v1/research-assets/{asset_id}/revisions
GET /api/v1/research-assets/{asset_id}/revisions/{revision_id}/members
PUT /api/v1/research-assets/{asset_id}/governance
POST /api/v1/research-assets/{asset_id}/catalog/publish
POST /api/v1/research-assets/{asset_id}/catalog/withdraw
POST /api/v1/research-assets/{asset_id}/archive
POST /api/v1/data-assets
GET /api/v1/data-assets/{data_asset_id}
PUT /api/v1/data-assets/{data_asset_id}
```

Validate:

- Default limit 20, maximum 100.
- Multi-value filters.
- Malformed cursor returns `400 invalid_cursor`.
- Detail endpoint requires `metadata:view`.
- Response bodies contain no protected keys.
- Unauthorized L4 list, detail, count, and autocomplete behavior does not reveal existence.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_research_catalog_api.py -q
```

- [ ] **Step 3: Implement thin endpoints**

Reuse the Phase 4 knowledge search route and map its response through the Explorer client; do not add a second search endpoint. Use stable lowercase filter values. Detail, revision-history, and member-manifest endpoints may expose richer safe catalog metadata but must exclude protected metadata, Source identity, external references, and storage details. Governance publication, withdrawal, archival, and DataAsset routes call their services and emit index and audit events; do not place transition logic in route handlers.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_research_catalog_api.py -q
git add backend/app/api/research_catalog.py backend/app/main.py backend/app/api/research_assets.py tests/test_research_catalog_api.py
git commit -m "feat: expose research data explorer api"
```

## Task 4: Make Project Linkage Context-Only

**Files:**

- Modify: `backend/app/services/research_asset_service.py`
- Modify: `backend/app/api/research_assets.py`
- Modify: `backend/app/services/access_request_service.py`
- Modify: `tests/test_research_assets.py`
- Create: `tests/test_project_asset_link_authorization.py`

- [ ] **Step 1: Write failing linkage tests**

Assert:

- Linking an asset never grants preview, download, agent use, or export.
- An authorized user cannot use an unlinked asset in a project.
- A linked and authorized asset is eligible.
- Removing a link immediately removes project eligibility.
- Final approval of a project-bound request creates the link if the approver is allowed to attach the asset.
- Approval does not create a link for a request without project context.
- Revoking the grant leaves the historical link but removes eligibility.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_project_asset_link_authorization.py -q
```

- [ ] **Step 3: Remove linkage from permission logic**

`can_user_link_asset_to_project` controls only link mutation. It must require:

- active project membership with sufficient project role;
- `metadata:view` for the asset;
- and either `asset:manage` or an approved project-bound request whose grant includes `content:use_in_agent`.

The link table remains:

```text
research_asset_id
project_id
linked_by
linked_at
```

Do not add capabilities to it.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_project_asset_link_authorization.py tests/test_research_assets.py -q
git add backend/app/services/research_asset_service.py backend/app/api/research_assets.py backend/app/services/access_request_service.py tests/test_project_asset_link_authorization.py tests/test_research_assets.py
git commit -m "fix: separate project links from access grants"
```

## Task 5: Route Project RAG Candidates Through KnowledgeQueryService

**Files:**

- Modify: `backend/app/services/knowledge_query_service.py`
- Modify: `backend/app/services/research_context.py`
- Modify: `backend/app/services/source_group_service.py`
- Test: `tests/test_rag_authorization_service.py`

- [ ] **Step 1: Write failing candidate authorization tests**

Test:

- Only linked, ready asset revisions are candidates.
- `content:use_in_agent` is required; preview or download alone is insufficient.
- Project-scoped policy must match the current project.
- Agent actor conditions are evaluated.
- Expired and revoked policies are denied immediately.
- Catalog-only members and non-ready revisions are excluded.
- Results include asset, revision, member, and chunk identity needed for citations and audit.
- A revision 1 grant never authorizes revision 2.
- Evaluation batches memberships and policies without N+1 queries.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_rag_authorization_service.py -q
```

- [ ] **Step 3: Implement the candidate contract**

```python
@dataclass(frozen=True)
class AuthorizedRagRevision:
    research_asset_id: UUID
    asset_revision_id: UUID
    member_ids: tuple[UUID, ...]
    title: str
    policy_ids: tuple[UUID, ...]
    grant_id: UUID | None
    authorization_expires_at: datetime | None
```

Required public signature: `async def authorize_project_rag_revisions(db: AsyncSession, *, user: User, project_id: UUID, requested_asset_ids: frozenset[UUID] | None, purpose: str, agent_run_id: UUID | None) -> tuple[AuthorizedRagRevision, ...]`.

Delegate candidate selection to `KnowledgeQueryService` in `project` scope. It begins from `ProjectAssetLink`, resolves eligible ready revisions, and applies `AccessContext(project_id=..., asset_revision_id=..., purpose=..., actor_type="agent")` before Qdrant retrieval.

Replace `collect_project_source_ids` and `expand_source_ids_for_rag` internals with this adapter. Do not preserve a legacy SourceShare or raw Source-ID fallback for agent use.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_rag_authorization_service.py tests/test_rag_service.py -q
git add backend/app/services/knowledge_query_service.py backend/app/services/research_context.py backend/app/services/source_group_service.py tests/test_rag_authorization_service.py
git commit -m "feat: authorize project rag sources"
```

## Task 6: Reauthorize Returned Chunks

**Files:**

- Modify: `backend/app/services/rag_service.py`
- Modify: `backend/app/services/vector_store.py`
- Modify: `backend/app/services/research_content_gateway.py`
- Test: `tests/test_rag_chunk_authorization.py`

- [ ] **Step 1: Write failing time-of-check tests**

Simulate:

- Candidate authorization succeeds.
- Grant is revoked or expires before vector results return.
- Unauthorized chunks are removed before response.
- No chunk text is logged or audited.
- A result with mismatched asset, revision, member, or chunk identity is rejected.
- All removed results produce a denial audit with IDs only.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_rag_chunk_authorization.py -q
```

- [ ] **Step 3: Change the RAG API contract**

Do not allow raw `source_ids` alone to authorize retrieval. Use:

Required public signature: `async def retrieve_authorized_chunks(*, db: AsyncSession, user: User, project_id: UUID, query: str, revisions: Sequence[AuthorizedRagRevision], purpose: str, agent_run_id: UUID | None, limit: int) -> list[RetrievedChunk]`.

After vector search:

1. Validate every payload asset/revision/member/chunk tuple against `revisions`.
2. Batch reauthorize exact revisions with current time.
3. Load chunk text only through `ResearchContentGateway` for the exact member with `content:use_in_agent`.
4. Drop denied chunks.
5. Audit allowed asset use once per asset and agent run, not once per chunk.

If all chunks are removed, return an empty result; never fall back to ungoverned retrieval.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_rag_chunk_authorization.py tests/test_rag_service.py -q
git add backend/app/services/rag_service.py backend/app/services/vector_store.py backend/app/services/research_content_gateway.py tests/test_rag_chunk_authorization.py
git commit -m "feat: reauthorize rag chunks before use"
```

## Task 7: Update WebSocket, Workflow, and Agent Callers

**Files:**

- Modify: `backend/app/api/websocket.py`
- Modify: `backend/app/api/agent_runtime.py`
- Modify: `backend/app/services/agent_runtime.py`
- Modify: `backend/app/services/agents/base.py`
- Modify: `backend/app/workflows/executor.py`
- Modify: `backend/app/workflows/builtin.py`
- Test: `tests/test_agent_data_governance.py`

- [ ] **Step 1: Write failing end-to-end agent tests**

Cover:

- Session in a project uses linked and authorized data.
- Same user in another project cannot use a project-scoped grant.
- Caller-supplied asset IDs cannot introduce an unlinked or unauthorized revision.
- An inaccessible but discoverable dataset may produce a metadata-only notice.
- The notice is exactly a safe statement such as “Internal data may support this hypothesis, but the current account cannot access its content.”
- Prompt context never contains protected metadata or inaccessible chunks.
- Agent run ID and project ID appear in audit events.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_agent_data_governance.py -q
```

- [ ] **Step 3: Pass explicit RAG context**

Every chat, workflow, and agent retrieval call must provide:

- authenticated user;
- project ID from the session;
- purpose derived from the user request or workflow objective;
- agent run ID when present;
- requested asset IDs as a narrowing filter only.

Remove calls that pass source IDs directly to `retrieve_chunks`.

- [ ] **Step 4: Add metadata-only evidence notices**

When catalog search finds discoverable evidence but agent content permission is denied, create a structured notice:

```python
@dataclass(frozen=True)
class InaccessibleEvidenceNotice:
    research_asset_id: UUID
    title: str
    classification: AssetClassification
    reason_code: str
```

Render it through localized UI metadata, not into the LLM prompt unless the title and classification are explicitly catalog-visible. Never include protected description fields.

- [ ] **Step 5: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_agent_data_governance.py tests/test_rag_service.py -q
git add backend/app/api/websocket.py backend/app/api/agent_runtime.py backend/app/services/agent_runtime.py backend/app/services/agents/base.py backend/app/workflows/executor.py backend/app/workflows/builtin.py tests/test_agent_data_governance.py
git commit -m "feat: govern agent research data use"
```

## Task 8: Add Governed Citations

**Files:**

- Modify: `backend/app/schemas/agent.py`
- Modify: `backend/app/schemas/agent_runtime.py`
- Modify: `frontend/src/types/agent.ts`
- Test: `tests/test_governed_citations.py`

- [ ] **Step 1: Write failing citation tests**

Assert:

- Accessible chunks cite ResearchAsset ID, exact revision, member, safe title, and chunk ID.
- Citation content preview URL is absent without `content:preview`.
- Citation download URL is absent without `content:download`.
- Catalog-only assets never produce chunk citations.
- A citation cannot be serialized if asset/revision/member/chunk identity is inconsistent.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_governed_citations.py -q
```

- [ ] **Step 3: Add citation shape**

```python
class GovernedCitation(BaseModel):
    research_asset_id: UUID
    asset_revision_id: UUID
    asset_content_member_id: UUID
    asset_title: str
    chunk_id: UUID
    preview_available: bool
    download_available: bool
```

The frontend builds action buttons from booleans and calls protected endpoints; the backend does not issue durable content URLs.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_governed_citations.py -q
cd frontend && npm run build
git add backend/app/schemas/agent.py backend/app/schemas/agent_runtime.py frontend/src/types/agent.ts tests/test_governed_citations.py
git commit -m "feat: add governed research citations"
```

## Task 9: Build the Research Data Explorer Page

**Files:**

- Create: `frontend/src/pages/ResearchDataExplorer.tsx`
- Create: `frontend/src/components/research-catalog/ResearchAssetCard.tsx`
- Create: `frontend/src/components/research-catalog/ResearchCatalogFilters.tsx`
- Create: `frontend/src/components/research-catalog/RequestAccessModal.tsx`
- Create: `frontend/src/components/research-catalog/RegisterDataAssetModal.tsx`
- Create: `frontend/src/api/research-catalog.ts`
- Create: `frontend/src/types/research-catalog.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`

- [ ] **Step 1: Add types and API client**

Mirror backend string unions exactly. Use React Query with the entire query/filter/cursor state in the query key.

Run:

```bash
cd frontend && npm run build
```

Expected: FAIL until route and components are complete.

- [ ] **Step 2: Build search and filters**

The page includes:

- debounced server-side search;
- classification, group, type, and access-state filters;
- cursor-based “load more”;
- empty, loading, error, and retry states;
- an access badge that distinguishes content available, metadata only, requestable, approval pending, and not requestable;
- category/subtype, current revision, member formats, and research-object relation summaries;
- upload and DataAsset registration actions only when the API reports the relevant management capability.

Do not filter a client-side copy of the old Library list.

- [ ] **Step 3: Build request flow**

`RequestAccessModal` requires:

- purpose;
- the exact requested revision;
- project when `content:use_in_agent` is selected;
- an end date bounded to 90 days for Internal/Confidential or 30 days for Restricted;
- allowed requestable capabilities only.

After submission, invalidate the catalog item, mine, and inbox query keys. Show the returned request status without assuming approval.

`RegisterDataAssetModal` captures scientific type/modality and safe scientific metadata. Managed files are added through upload/revision intake. External URL or DOI registration uses the metadata-only endpoint and offers a separate explicit snapshot action; the UI never reads ciphertext or a decrypted reference back.

The detail drawer shows immutable revision history and the safe member manifest. Content actions always carry `asset_id`, `revision_id`, and `member_id`; changing the selected revision recomputes access state and never assumes the current revision grant applies.

- [ ] **Step 4: Add navigation and i18n**

Add a lazy-loaded `/research-data` route and navigation entry. Keep the existing Library route as a management-focused view. All English and Chinese text lives in locale JSON.

- [ ] **Step 5: Build and commit**

```bash
cd frontend && npm run build
git add frontend/src/pages/ResearchDataExplorer.tsx frontend/src/components/research-catalog frontend/src/api/research-catalog.ts frontend/src/types/research-catalog.ts frontend/src/App.tsx frontend/src/locales/en-US.json frontend/src/locales/zh-CN.json
git commit -m "feat: add research data explorer"
```

Expected: PASS.

## Task 10: Build Access Request Center

**Files:**

- Create: `frontend/src/pages/AccessRequestCenter.tsx`
- Create: `frontend/src/components/access-requests/AccessRequestDetail.tsx`
- Create: `frontend/src/api/access-requests.ts`
- Create: `frontend/src/types/access-request.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`

- [ ] **Step 1: Add type-safe API hooks**

Implement query hooks for mine, inbox, and detail, plus mutations for approve, reject, cancel, and revoke.

- [ ] **Step 2: Build requester and approver views**

The page has:

- “My requests” and “Approval inbox” tabs;
- status, exact revision, requested capabilities, project, purpose, duration, and safe asset metadata;
- approve/reject actions only when the API says `can_decide=true`;
- required rejection reason;
- cancellation for pending requester-owned requests;
- active-grant revocation for authorized stewards.

Do not display protected metadata or requester purpose to users who are not eligible approvers.

- [ ] **Step 3: Add route and translations**

Add lazy-loaded `/access-requests`. Show a pending count from the inbox endpoint. Use i18n for every label, state, validation error, and notification.

- [ ] **Step 4: Build and commit**

```bash
cd frontend && npm run build
git add frontend/src/pages/AccessRequestCenter.tsx frontend/src/components/access-requests frontend/src/api/access-requests.ts frontend/src/types/access-request.ts frontend/src/App.tsx frontend/src/locales/en-US.json frontend/src/locales/zh-CN.json
git commit -m "feat: add research access request center"
```

## Task 11: Integrate Explorer Assets with Project Sessions

**Files:**

- Modify: `frontend/src/pages/ProjectAssets.tsx`
- Modify: `frontend/src/pages/ResearchDataExplorer.tsx`
- Modify: `frontend/src/components/library/AssetDetailDrawer.tsx`
- Modify: `frontend/src/types/research-asset.ts`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`

- [ ] **Step 1: Add permission-aware actions**

For each asset:

- show “Add to project” only when linking is allowed;
- show “Request agent access” for the selected revision when link exists or can be requested but agent capability is absent;
- show “Available in project RAG” only when the selected revision is linked-eligible and currently authorized;
- show expiry when capability is time-bound;
- never show preview/download actions without their matching live capabilities.

- [ ] **Step 2: Handle permission changes**

React Query invalidation must refresh asset access state after:

- link or unlink;
- request submission;
- approval or rejection;
- revocation;
- governance/classification update.
- current-revision change.

The server remains authoritative; do not optimistically grant content actions.

- [ ] **Step 3: Build and commit**

```bash
cd frontend && npm run build
git add frontend/src/pages/ProjectAssets.tsx frontend/src/pages/ResearchDataExplorer.tsx frontend/src/components/library/AssetDetailDrawer.tsx frontend/src/types/research-asset.ts frontend/src/locales/en-US.json frontend/src/locales/zh-CN.json
git commit -m "feat: connect governed assets to projects"
```

## Task 12: Capture Generated Knowledge and Research Memory as Assets

**Files:**

- Create: `backend/app/services/research_asset_capture_service.py`
- Modify: `backend/app/services/task_service.py`
- Modify: `backend/app/api/research_objects.py`
- Modify: `backend/app/api/sessions.py`
- Test: `tests/test_research_asset_capture.py`

- [ ] **Step 1: Write failing capture tests**

Cover:

- A completed task report, literature review, experiment design, or analysis report can be published as a `generated_document` asset revision.
- A user can publish selected hypotheses, evidence, conclusions, and object relations as a `research_memory` snapshot revision.
- A user can explicitly save a conversation summary, note, draft, or conclusion as a `conversation_artifact`; ordinary chat messages are never auto-published.
- SOP, protocol, experiment record, and experiment-data description uploads use `experimental_material`.
- Every capture requires governance context, records provenance to the originating task/session/research objects, emits knowledge events after sealing, and becomes globally metadata-searchable.
- Protected source content is never copied into safe catalog metadata.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_research_asset_capture.py -q
```

- [ ] **Step 3: Implement one capture service**

Required public signature:

```python
async def capture_research_asset(
    db: AsyncSession,
    *,
    actor: User,
    category: Literal[
        "generated_document",
        "research_memory",
        "conversation_artifact",
    ],
    title: str,
    rendered_content: str,
    provenance: AssetProvenance,
    governance: GovernanceCreationContext,
) -> AssetRevision
```

The service creates or appends to a ResearchAsset, stores rendered content through the existing local Source abstraction as a generated member, seals the revision, and emits catalog/revision events transactionally. Provenance stores identifiers and relation types, not copied protected text. Callers must perform an explicit publish/save command; drafts remain outside the catalog.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_research_asset_capture.py tests/test_knowledge_index_event_service.py -q
git add backend/app/services/research_asset_capture_service.py backend/app/services/task_service.py backend/app/api/research_objects.py backend/app/api/sessions.py tests/test_research_asset_capture.py
git commit -m "feat: capture generated research knowledge"
```

## Task 13: End-to-End Governance Verification

**Files:**

- Create: `tests/test_research_data_governance_e2e.py`

- [ ] **Step 1: Write the complete backend scenario**

Create two groups, four users, five classifications, two revisions of a restricted dataset, a catalog-only scientific asset, a generated report, saved research memory, a project link, and an access workflow.

Verify:

1. Global knowledge search without a project returns permitted cross-group metadata for uploaded, generated, memory, and scientific assets.
2. Restricted content is denied before approval.
3. Request submission and PI approval create an expiring grant for revision 1.
4. Approved linked revision 1 enters project RAG.
5. The same content is unavailable in an unrelated project.
6. Revocation removes it from RAG immediately.
7. Catalog-only content never enters RAG.
8. Revision 2 remains unavailable under the revision 1 grant.
9. Grant and revocation do not change vector point counts.
10. Audit events cover every transition.

- [ ] **Step 2: Run the scenario**

```bash
backend/.venv/bin/python -m pytest tests/test_research_data_governance_e2e.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full verification**

```bash
backend/.venv/bin/python -m pytest -q
cd frontend && npm run build
git diff --check
pre-commit run
```

Expected: PASS.

- [ ] **Step 4: Inspect direct RAG and content access**

```bash
rg -n "retrieve_chunks\\(|_rag_chunks\\(|FileResponse|can_user_access_source|can_user_read_asset" backend/app
```

Every remaining call must delegate to the governed authorization and content gateway path. No direct protected-content read may remain.

- [ ] **Step 5: Commit final verification**

```bash
git add tests/test_research_data_governance_e2e.py
git commit -m "test: verify research data governance"
```

If verification required production fixes, stage those exact files too and use a commit message that describes the fix instead of hiding it in the test commit.
