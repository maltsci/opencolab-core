# Upload-Time Research Asset Classification

## Context

The lab library upload controls currently expose only legacy visibility scopes:
`lab_public` and `lab_private`. Visibility determines catalog discovery, but it
does not express the research data sensitivity level. New library uploads
therefore default to `internal`, and users cannot explicitly create
`confidential`, `restricted`, or `top_secret` assets from the page.

## Goals

- Let every uploader explicitly classify new research assets.
- Keep catalog visibility and data classification as independent controls.
- Default new uploads to `internal`.
- Apply one selected classification to every asset produced by a ZIP upload.
- Show the resulting classification in the library list and asset detail drawer.
- Preserve the existing rule that only PI and Admin users may lower an existing
  asset's classification.

## Non-Goals

- Implementing the access request and approval user interface.
- Changing existing assets automatically.
- Replacing legacy visibility scopes in this iteration.
- Adding classification-specific policy templates beyond the current access
  policy engine.

## User Experience

The library upload controls contain two adjacent selects:

1. **Visibility**: Lab Public or Lab Private.
2. **Data Classification**: Public, Internal, Confidential, Restricted, or Top
   Secret.

The classification select defaults to Internal. All uploaders may choose any
classification because users must be able to protect data conservatively at the
time of ingestion. Existing governance rules continue to restrict later
classification lowering to PI and Admin users.

The library asset table adds a Data Classification column. The asset detail
drawer also shows the classification. Labels and option descriptions use the
existing English and Simplified Chinese translation files.

## API Design

`POST /api/v1/library/assets/upload` accepts a new multipart form field:

```text
classification=internal
```

Allowed values:

- `public`
- `internal`
- `confidential`
- `restricted`
- `top_secret`

The field is optional for backward compatibility and defaults to `internal`.
Invalid values return HTTP 400 before file processing begins.

After source materialization and before publication, the endpoint assigns the
validated classification to every created asset. This includes every file and
collection asset produced by a ZIP upload. The existing visibility field
continues to control catalog publication independently.

## Security Rules

- Classification is validated server-side.
- Selecting Public does not override visibility or grant content capabilities.
- Selecting a high classification does not automatically grant other users
  access.
- The uploader retains only the existing revision-specific owner policy.
- Top Secret discovery and content access continue to use the centralized
  access policy evaluator.

## Error Handling

- Invalid classification: HTTP 400 with `Invalid classification`.
- Existing upload validation, duplicate handling, and ZIP errors remain
  unchanged.
- If upload processing fails, no special classification fallback is applied.

## Testing

Backend tests verify:

- A Confidential upload persists `classification=confidential`.
- A Restricted upload persists `classification=restricted`.
- Every asset created from a ZIP receives the selected classification.
- Invalid classification values return HTTP 400.
- Omitting the field preserves the Internal default.

Frontend verification covers:

- TypeScript production build succeeds.
- The upload request contains the selected classification.
- The library list and detail drawer render translated classification labels.

## Compatibility

Existing API clients that omit `classification` continue to create Internal
library assets. No database migration is required because the classification
column and governance enums already exist.
