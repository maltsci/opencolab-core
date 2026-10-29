# Library Permission-Aware Search Design

## Goal

Add a laboratory-wide library search that allows researchers to discover relevant
assets without weakening content access controls.

The search must provide two clearly separated result groups:

- **Full-text searchable** assets: users can see semantic text matches and open
  the source because they have content permission.
- **Request access** assets: users can discover only the approved catalog fields
  and can request access. No source text, abstract, file details, page numbers,
  chunk IDs, scores, or semantic snippets are exposed.

Users can link an accessible asset to a project from a search result. When a
private asset needs approval, the access request records the target project and
the link is created when the request is approved.

## Scope

### Included

- Search across laboratory-visible assets.
- Metadata search limited to title, authors, tags, steward, project, and date.
- Permission-filtered semantic full-text search for authorized assets.
- Grouped search results and explicit access states.
- Project linking from search results.
- Request access with an optional target project, followed by automatic linking
  on approval.

### Excluded

- Changing the PDF parsing pipeline or vector embedding model.
- Replacing Qdrant with a new search platform.
- Changing ownership, publication, or sharing policies when a project link is
  created.
- Making restricted content available to a project before the requester has a
  valid content grant.

## Existing Foundations

The implementation extends current components rather than introducing a second
asset or permission system.

| Existing component | Reuse in this feature |
| --- | --- |
| `research_assets` | Catalog fields, lifecycle state, owner/steward, source identity, and access policy target. |
| `project_asset_links` | The sole relationship for associating an asset with a project. Its unique constraint makes linking idempotent. |
| `access_requests` | Access approval workflow; add an optional target project reference. |
| `access_policy_service` | Server-side catalog discovery and content-use decisions. |
| Qdrant and `rag_service` | Semantic retrieval for sources whose owning assets have already passed content authorization. |

## Permission and Search Model

### Catalog discovery

Catalog discovery is evaluated per asset through the existing access policy
service. An asset that is discoverable may appear in the catalog group, subject
to the visibility and lifecycle filters already used by the library.

The catalog response is an allowlist, not a redacted full asset response. It may
contain only:

- title
- authors
- tags
- steward or responsible person
- linked or origin project name
- relevant date

The server must not derive a response from `description`, `metadata_json`, source
records, chunks, or a vector result and then attempt to remove forbidden fields.

### Full-text search

Full-text search uses the existing Qdrant collection. It does not require a new
search engine.

For each request, the backend performs the following sequence:

1. Query PostgreSQL for active, discoverable library assets matching catalog
   filters and resolve the current user’s `CONTENT_USE_IN_AGENT` capability for
   each candidate asset.
2. Build the allowed `source_id` set only from assets with content permission.
3. Pass that source set to the existing vector search, which already accepts a
   source filter.
4. Load matching chunks from PostgreSQL and re-check the asset content decision
   before constructing a full-text result.
5. Merge results into two response groups: `full_text_results` and
   `catalog_results`.

This order is mandatory. A source without content permission must never be sent
to the vector query as a candidate, even if the caller can discover its catalog
record.

### Result grouping

The UI presents groups instead of a mixed list:

1. **Full-text searchable**: title, permitted metadata, a semantic match snippet,
   status, open action, and “Link to project”.
2. **Request access**: title and the six catalog allowlist fields only. The card
   displays no snippet and uses “Request access and link” when the user selects
   a project.

The UI labels the groups and access state so a user can distinguish a content
match from a catalog discovery result.

## API and Data Changes

### Search endpoint

Add a library search endpoint under the research-assets API namespace. It accepts
a query, optional catalog filters, pagination, and an optional semantic-search
mode. The endpoint returns a grouped response rather than a flat asset list.

The full-text result item includes only data that is already allowed by content
permission: asset identity, safe display metadata, a matching snippet, and the
source/open reference. The catalog result item uses a dedicated schema with the
six allowlisted fields and request state.

The endpoint must have a deterministic error response for an unavailable vector
service: catalog results remain available and the response includes a
`full_text_search_available: false` status. It must not broaden vector search or
return cached content from unauthorized assets.

### Access request target project

Reuse the existing nullable `project_id` on `access_requests`, referencing
`projects`, as the optional target project. Add the equivalent request and
response schema field where it is not already exposed.

Creation rules:

- The requester must be able to discover the asset.
- The requester must be a member of the target project when one is supplied.
- The request records the target project and its normal purpose/duration.
- Repeated active requests for the same asset and requester remain rejected or
  returned idempotently; they must not create duplicate links.

Approval rules:

- Resolve the current asset revision and grant content capabilities as today.
- When `project_id` is present, verify the requester still belongs to the
  project and can link the asset to it.
- Create the `ProjectAssetLink` with `link_type="reference"`.
- Save the request decision, access policy, and project link in one transaction.
- If the project membership or link authorization no longer holds, do not issue
  a partial grant/link. Return a clear conflict requiring the requester to
  resubmit against an eligible project.

Direct linking uses the existing `bulk-link` capability with a single asset and
single project, or a narrow single-link endpoint that delegates to the same
authorization service. It does not alter asset ownership, visibility, or policy.

### Metadata normalization

The search service reads search/display fields from a controlled catalog mapping.
It must normalize the current catalog payloads into this logical shape:

```text
title, authors, tags, steward_name, project_name, date
```

Assets missing an optional value can still be returned. Their missing value is
not filled from protected metadata or extracted document text. A later migration
or ingestion enhancement may populate these fields, but search behavior must be
safe before all historical assets are backfilled.

## Frontend Interaction

1. User enters a query in the library search.
2. The result view displays full-text results first, with matching snippets and
   “Link to project”.
3. Selecting “Link to project” opens a project selector filtered to projects the
   user can join/link to. On success, the card shows the project association.
4. Catalog-only results are shown in a separate group. Each card explicitly says
   that only catalog information is visible.
5. Selecting “Request access and link” opens the request dialog with the target
   project selector, purpose, and duration.
6. After approval, the asset appears in the selected project’s assets list and
   becomes eligible for project context only while its content grant is valid.

An expired or revoked grant leaves the relationship visible in the project asset
list with an access-expired state. It is excluded from full-text retrieval and
project-agent context until access is restored.

All new strings use existing frontend i18n resources.

## Failure and Security Cases

| Situation | Required behavior |
| --- | --- |
| User lacks discovery permission | Return no asset indication; use the existing not-found behavior. |
| User can discover but lacks content permission | Return only the catalog allowlist; never return snippets, similarity scores, source IDs, or content errors. |
| Qdrant/embedding service unavailable | Return catalog matches and an explicit full-text-search-unavailable status. |
| Access request already pending or active | Avoid duplicate request/link creation and show the existing request state. |
| Asset already linked | Return a successful idempotent link result. |
| Approval after project membership changed | Do not grant or link partially; return a conflict for resubmission. |
| Grant expires or is revoked | Retain link record but block content preview, retrieval, and agent use. |

## Test Plan

### Backend

- A discoverable private asset returns only the catalog allowlist to a user
  without content permission.
- Its source ID and chunks are absent from the vector-search filter and response.
- An authorized asset is eligible for semantic retrieval and returns a permitted
  snippet.
- A user cannot link an asset to a project they do not belong to.
- A user with access can link an asset once; a second request is idempotent.
- A request with a target project, when approved, creates both policy grant and
  project link atomically.
- Approval fails without partial writes if membership changes before approval.
- Expired grants exclude the asset from semantic search and agent context.
- Vector-service failure preserves catalog results and does not expose content.

### Frontend

- Results render in separate full-text and catalog-only groups.
- Catalog-only cards never render a snippet/open-content action.
- Link action presents only eligible projects.
- Request dialog persists the chosen project and updates request state.
- i18n coverage exists for loading, empty, unavailable, requested, linked, and
  expired states.

## Rollout

1. Ship the backend schemas, authorization tests, and endpoint behind a feature
   flag if deployment requires staged exposure.
2. Enable the search UI for library users after permission tests pass.
3. Observe search and request errors through existing application logs without
   logging query text or protected metadata.
4. Backfill optional authors/tags/steward/project/date catalog fields gradually;
   missing fields must not block safe discovery.
