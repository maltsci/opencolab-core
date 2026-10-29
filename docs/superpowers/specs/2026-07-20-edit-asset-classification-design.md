# Edit Existing Asset Classification Design

## Context

OpenColab lets an uploader choose a data classification when a laboratory asset
is created, but an existing asset has no classification-editing interaction.
The backend already exposes a governance update endpoint, although its current
authorization and reason rules do not match the approved lightweight workflow.

This design adds a controlled classification change interaction to the asset
detail drawer without exposing policy internals or broadening unrelated asset
management permissions.

## Goals

- Let an eligible user change the classification of an existing Research Asset.
- Put the interaction in the asset detail drawer.
- Enforce the same authorization rule in the API and the UI.
- Require a reason when a change lowers protection.
- Keep a protected lightweight record of each classification change.
- Refresh both the detail drawer and the containing asset list after success.

## Non-Goals

- Editing access policies, grants, agreements, owning groups, or stewards.
- Building the complete append-only governance audit subsystem.
- Adding a list-row quick edit action.
- Changing classification discovery or content-access semantics.
- Changing an asset's catalog scope or publication status.

## Permission Model

Classification changes use a dedicated capability response,
`can_change_classification`. The UI must not infer this capability from
`can_publish`, `can_withdraw`, visibility scope, or the presence of an edit
button.

An active user may change classification when at least one condition is true:

1. the user is the asset `owner_id`;
2. the user is the asset `steward_user_id`;
3. the user is an active PI member of the asset's `owning_group_id`;
4. the user is a system Admin.

An owning-group PI cannot change an asset owned by another research group.
For a legacy asset without `owning_group_id`, only its owner, steward, or a
system Admin is eligible. A global PI role alone does not grant access to
ungrouped or other-group assets.

The API performs this authorization independently. Hiding the UI action is not
a security boundary.

## Classification Change Rules

The ordered classifications are:

1. `public`;
2. `internal`;
3. `confidential`;
4. `restricted`;
5. `top_secret`.

A move to a higher number increases protection. A move to a lower number
decreases protection.

- Increasing protection: the reason is optional.
- Decreasing protection: a non-blank reason is required.
- Selecting the current classification is not submitted.
- Every successful change sets `governance_review_status` to `pending`.
- The change takes effect immediately for subsequent authorization decisions.

The approved workflow intentionally allows the asset owner or steward to lower
classification. This is a phase-one product decision and overrides the earlier
governance-foundation rule that limited lowering to PI/Admin users.

## User Experience

The asset detail drawer continues to show the current classification tag.

When `can_change_classification` is true, a text-style **Change** action appears
next to the tag. Selecting it opens a modal containing:

- the current classification;
- a target classification selector;
- a reason text area;
- an inline warning when the target lowers protection;
- Cancel and Confirm actions.

When the target increases protection, the reason field is labeled optional.
When the target lowers protection, the reason field becomes required and the
modal explains that lowering protection may expand metadata or content access.

The Confirm action remains disabled when:

- no different target classification is selected;
- a downgrade reason is blank;
- a request is already being submitted.

On success:

- close the modal;
- replace the drawer asset with the API response;
- refresh the parent laboratory or project asset list;
- show a localized success message.

On failure:

- keep the modal open;
- preserve the user's target and reason;
- show the server detail when safe, otherwise a localized generic failure;
- treat a 403 response as an authorization failure.

Users without the capability see only the classification tag.

## API Contract

Catalog list and authorized detail responses add:

```json
{
  "can_change_classification": true
}
```

Classification changes use a dedicated endpoint:

```http
PUT /api/v1/research-assets/{asset_id}/classification
```

The classification update payload is:

```json
{
  "classification": "restricted",
  "governance_reason": "Partner agreement now restricts reuse"
}
```

For an upgrade, `governance_reason` may be omitted or null. For a downgrade, it
must contain non-whitespace text. The endpoint returns the updated safe catalog
response, including `can_change_classification`, and never returns
`protected_metadata_json`, `source_id`, policy details, or storage information.

The existing general governance endpoint remains restricted to its current
full-governance managers. Classification eligibility does not grant permission
to edit protected metadata, stewardship, ownership, lifecycle, policy, or
catalog fields.

Expected errors:

- `400`: invalid classification, unchanged classification, or missing downgrade
  reason;
- `403`: the authenticated user cannot change this asset's classification;
- `404`: the asset does not exist or is not discoverable to the caller;
- `409`: the asset is not in an active lifecycle state.

## Lightweight Change Record

Until the append-only governance audit subsystem is implemented, each
successful change appends a record to a protected metadata list that is never
included in catalog responses:

```json
{
  "classification_changes": [
    {
      "from": "internal",
      "to": "restricted",
      "reason": "Partner agreement now restricts reuse",
      "changed_by": "user-id",
      "changed_at": "2026-07-20T10:00:00Z"
    }
  ]
}
```

This is an interim operational record, not a substitute for the future
append-only audit event table. It must remain in `protected_metadata_json` and
must not be copied into catalog metadata.

## Component Boundaries

### Backend authorization helper

A focused helper decides whether a user can change classification. It depends
on the asset owner, steward, owning-group membership, active user role, and
Admin role. It does not grant publish, withdraw, preview, download, or Agent
capabilities.

### Governance endpoint

The dedicated classification endpoint validates the transition, checks the
dedicated authorization helper, appends the protected change record, updates
the review status, commits, and returns a safe catalog response. It is separate
from the general governance endpoint so that classification authority never
exposes or mutates unrelated protected governance fields.

### Classification change modal

A focused frontend component owns target selection, downgrade detection, reason
validation, submission state, and localized warning/error copy. The detail
drawer only decides whether to render the trigger and forwards the successful
asset response to its parent.

### Parent pages

The laboratory and project asset pages provide a callback that updates the
currently selected asset and reloads their list after a successful change.

## Testing

Backend tests cover:

- owner may increase classification without a reason;
- owner may decrease classification with a reason;
- owner decrease without a reason returns 400;
- steward may change classification;
- owning-group PI may change classification;
- PI from another group receives 403;
- PI cannot use the global role alone for an ungrouped legacy asset;
- Admin may change any active asset;
- ordinary group member receives 403;
- a successful change sets review status to pending;
- a successful change appends a protected change record;
- catalog responses never expose the protected record;
- response capability matches the endpoint authorization decision.

Frontend/build verification covers:

- the trigger is visible only when the capability is true;
- upgrade reason is optional;
- downgrade reason is required and warning copy is visible;
- a successful update refreshes the drawer and parent list;
- a failed request preserves form state;
- production TypeScript and Vite builds succeed.
