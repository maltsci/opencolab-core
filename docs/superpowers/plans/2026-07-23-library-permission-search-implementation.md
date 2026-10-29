# Library Permission-Aware Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver laboratory-wide metadata discovery and permission-filtered full-text search, including project linking and request-then-link workflows.

**Architecture:** Reuse `ResearchAsset`, `ProjectAssetLink`, `AccessRequest`, the policy service, and Qdrant. PostgreSQL performs catalog discovery with a strict metadata allowlist; Qdrant receives only source IDs whose assets are authorized for content use. The API returns separate full-text and catalog-only result groups.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, PostgreSQL, Qdrant, React, TypeScript, Ant Design, pytest.

---

## Baseline

The working tree already contains uncommitted access-request and asset governance
changes. Treat those files as the approved starting point. Do not reset, discard,
or stage unrelated changes. This plan adds only the behavior specified in
`docs/superpowers/specs/2026-07-23-library-permission-search-design.md`.

### Task 1: Carry the target project through access requests

**Files:**
- Modify: `backend/app/models/access_request.py`
- Modify: `backend/app/schemas/research_asset.py`
- Modify: `backend/app/api/research_assets.py`
- Test: `tests/test_research_assets.py`

- [x] **Step 1: Write the failing request-and-approval test**

```python
async def test_access_request_approval_links_the_selected_project(...):
    request_response = await client.post(
        f"/api/v1/research-assets/{asset.id}/access-requests",
        json={"purpose": "Use in my study", "duration_days": 30,
              "project_id": project.id},
        headers=researcher_headers,
    )
    assert request_response.status_code == 201
    assert request_response.json()["project_id"] == project.id

    approval = await client.post(
        f"/api/v1/research-assets/access-requests/{request_response.json()['id']}/approve",
        json={}, headers=pi_headers,
    )
    assert approval.status_code == 200
    assert await db.scalar(select(ProjectAssetLink).where(
        ProjectAssetLink.asset_id == asset.id,
        ProjectAssetLink.project_id == project.id,
    )) is not None
```

- [x] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_research_assets.py::test_access_request_approval_links_the_selected_project -v`

Expected: FAIL because `project_id` is not accepted or returned and no link is created.

- [x] **Step 3: Expose the existing target-project data through the model and API**

Reuse the existing nullable `project_id` column created by the access-request
migration. Add the field to the SQLAlchemy model and to
`AssetAccessRequestCreate` and `AssetAccessRequestResponse`.

- [x] **Step 4: Validate and create the project link during approval**

In request creation, require current requester membership for a supplied project.
In approval, revalidate requester membership and `can_user_link_asset_to_project`.
Call `link_asset_to_project` after creating the grant and before the one existing
`commit`. Return a conflict before writes if the project is no longer eligible.

- [x] **Step 5: Re-run the targeted test**

Run: `pytest tests/test_research_assets.py::test_access_request_approval_links_the_selected_project -v`

Expected: PASS.

### Task 2: Add a permission-aware library search service

**Files:**
- Create: `backend/app/services/library_search_service.py`
- Modify: `backend/app/schemas/research_asset.py`
- Modify: `backend/app/api/research_assets.py`
- Test: `tests/test_research_assets.py`

- [x] **Step 1: Write a failing catalog-boundary test**

```python
async def test_library_search_returns_private_asset_as_catalog_only(...):
    response = await client.get(
        "/api/v1/library/assets/search", params={"query": "private peptide"},
        headers=researcher_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["full_text_results"] == []
    result = next(item for item in body["catalog_results"] if item["id"] == asset.id)
    assert set(result) <= {
        "id", "title", "authors", "tags", "steward_name", "project_name",
        "date", "can_request_access", "active_access_request_status",
    }
    assert "FULL SECRET RESULT" not in response.text
```

- [x] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_research_assets.py::test_library_search_returns_private_asset_as_catalog_only -v`

Expected: FAIL because the search route and grouped response do not exist.

- [x] **Step 3: Define dedicated search schemas**

Create catalog and full-text item schemas plus one grouped response schema. The
catalog schema is an allowlist containing only title, authors, tags, steward,
project, date, and request state. Do not reuse `ResearchAssetResponse`.

- [x] **Step 4: Implement the minimal safe search service**

Query active discoverable lab assets from PostgreSQL. Match query text only
against normalized catalog fields. For every candidate, call the existing content
authorization helper. Build the vector source filter from content-authorized
assets only. Use `_rag_chunks` for semantic matches, then revalidate the matched
asset before producing a snippet. Return remaining discoverable matches as
catalog-only results.

- [x] **Step 5: Add the API route and verify the boundary test**

Run: `pytest tests/test_research_assets.py::test_library_search_returns_private_asset_as_catalog_only -v`

Expected: PASS.

### Task 3: Verify authorized retrieval and degraded vector behavior

**Files:**
- Modify: `backend/app/services/library_search_service.py`
- Test: `tests/test_research_assets.py`

- [x] **Step 1: Write two failing tests**

```python
async def test_library_search_returns_snippet_only_for_authorized_asset(...):
    # Grant content access and monkeypatch _rag_chunks to return a known chunk.
    assert result["full_text_results"][0]["snippet"] == "AUTHORIZED RESULT"

async def test_library_search_keeps_catalog_results_when_vector_search_fails(...):
    # Make _rag_chunks raise an expected search-service exception.
    assert result["full_text_search_available"] is False
    assert result["catalog_results"]
```

- [x] **Step 2: Run both tests to verify they fail**

Run: `pytest tests/test_research_assets.py -k "library_search_returns_snippet or library_search_keeps_catalog" -v`

Expected: FAIL because authorized snippets and degraded status are not implemented.

- [x] **Step 3: Implement content result construction and safe degradation**

Expose snippets only for assets that passed content authorization. Catch only
search transport/runtime failures around vector retrieval, log no query text or
protected metadata, set `full_text_search_available=False`, and still return
catalog matches.

- [x] **Step 4: Re-run both tests**

Run: `pytest tests/test_research_assets.py -k "library_search_returns_snippet or library_search_keeps_catalog" -v`

Expected: PASS.

### Task 4: Add library search and project-link interaction

**Files:**
- Modify: `frontend/src/types/research-asset.ts`
- Modify: `frontend/src/pages/Library.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`

- [x] **Step 1: Add TypeScript types and i18n keys**

Define response types matching the dedicated backend schemas. Add English and
Chinese translations for result groups, full-text unavailable, catalog-only,
link-to-project, request-and-link, target project, and linked state.

- [x] **Step 2: Add the search controls and grouped cards**

Use the project’s existing API client and Ant Design controls. Render a search
input above the library tabs, then separate full-text and catalog result sections.
Catalog cards must not render snippets or open-content actions.

- [x] **Step 3: Add direct linking and request-with-project selection**

Use the existing project list to populate the project selector. Direct links call
the existing bulk-link endpoint with one asset and one project. The existing
access request modal includes `project_id` when launched from search.

- [x] **Step 4: Build the frontend**

Run: `npm run build`

Expected: PASS.

### Task 5: Final verification

**Files:**
- Test: `tests/test_research_assets.py`

- [x] **Step 1: Run targeted backend coverage**

Run: `pytest tests/test_research_assets.py -v`

Expected: PASS.

- [x] **Step 2: Run formatting and frontend build checks**

Run: `pre-commit run --files backend/app/models/access_request.py backend/app/schemas/research_asset.py backend/app/api/research_assets.py backend/app/services/library_search_service.py frontend/src/pages/Library.tsx frontend/src/types/research-asset.ts frontend/src/locales/en-US.json frontend/src/locales/zh-CN.json tests/test_research_assets.py`

Run: `npm run build`

Expected: PASS.

- [ ] **Step 3: Review staged scope before committing**

Run: `git diff --check && git status --short`

Expected: only task-related files are staged; retain pre-existing unrelated
working-tree changes unstaged.
