# Lab Knowledge OS v1 — Phase 1: Resources

**Goal:** Extend the existing research-asset library into the approved Resources catalog without creating a second asset system or weakening current access controls.

**Entry evidence:** Phase 0 has a stable `ResearchAsset` governance model, `ResearchDirection` identifiers, `ResearchAssetDirection` relation table, scoped Steward authority, and request-time access checks.

## Scope

This phase turns a discoverable research asset into a resource entry that can show:

- purpose, suitable use, limitations, and an access/request instruction;
- current steward, resource type, visibility, and processing state;
- explicit active Research Direction associations;
- last confirmation and review-due dates, including an actionable stale state;
- existing access-request and project-linking paths when content or a protected address is unavailable.

The data/code/model/GPU matrix uses the stable common fields above. Type-specific operational fields remain in `catalog_metadata_json` and are displayed as a compact optional note in a later slice after the lab supplies a real inventory sample. This avoids prematurely designing a rigid GPU or model schema.

## Non-goals

- No new `Resource` entity, migration, graph database, real-time GPU status, credential storage, or external synchronization.
- No People, Research directory, Assistant, notification, or activity-projection work.
- No bypass of `ResearchAsset` discovery, content, access-request, publishing, or project-link rules.

## Vertical delivery slices

### Slice 1 — Resource profile contract

1. Add red tests for viewing a discoverable resource profile, current-public metadata, and permission-gated protected location information.
2. Add a validated profile read/update service over `ResearchAsset.catalog_metadata_json`; only an existing asset manager can update it.
3. Add tests and an API route that rejects secret-like field names and never exposes protected data to a metadata-only user.

### Slice 2 — Resource–direction associations

1. Add red tests for listing, creating, and removing an association, including active-direction, duplicate, and scoped-Steward constraints.
2. Reuse `ResearchAssetDirection` and `can_govern_asset_direction`; do not add a parallel association table.
3. Return direction name and association purpose so the catalog page can render a human-readable link.

### Slice 3 — Resources page

1. Adapt the existing `/library` experience into the Resources surface, preserving uploads, access requests, source collections, and project linking.
2. Add a resource-profile section to the existing detail drawer with purpose, steward, direction links, access path, freshness state, and distinct empty/permission/stale states.
3. Rename navigation and localized copy from Lab Library/资料库 to Resources/资源 while retaining the URL for backwards compatibility.

## Exit criteria

- A member can find a key resource by name/type/visibility, open its detail, understand its purpose and next access step, and see its direction links.
- A resource manager or scoped Steward can maintain the allowed fields and direction links; an unauthorized member cannot.
- Access requests, project links, publication, withdrawn resources, and current permission filtering have no regressions.
- The page provides explicit empty, permission-limited, withdrawn, processing, and stale-information states.
- Backend behavior tests and frontend type/build checks pass. The branch is then eligible for local fast-forward merge into `public-one` for browser acceptance.

## Manual acceptance data

Before pilot release, a PI or Steward must enter at least one real key resource for each available class (for example data, code, model, or GPU) and confirm its purpose, maintainer, access instructions, direction relation, and review date. No fabricated lab resource records are committed to Git.
