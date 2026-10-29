# Sharing & Permissions

OpenColab implements a per-source ownership and sharing model. Every source (file, group, or note) has an owner and can optionally be shared with other users.

## Core Concepts

### Ownership

Every source has an `owner_id` that tracks who created it. Ownership determines who can share, rename, or delete a source. When a user uploads a file, creates a group, or saves a note, they become the owner.

### Sharing

A source can have at most **one share record** (`SourceShare`). Sharing is configured with two dimensions:

- **Scope** — who can see the source:
  - `all` — visible to all users in the system
  - `project` — visible only to members of a specific project
- **Permission** — what non-owners can do:
  - `read` — view only
  - `readwrite` — can modify (e.g., add/remove members in groups, edit notes)

### Display Name

Users can set a `display_name` via `PATCH /api/v1/auth/me`. This name appears in the UI header, in share metadata (`shared_by_name`), and as the `owner_name` on source responses. Falls back to `username` when unset.

## Behavior by Source Type

### Files

| Action | Rule |
|---|---|
| Default visibility | Private (owner only) |
| Share | Owner can share; permission is always forced to `read` |
| Unshare | **Not allowed** — files cannot be unshared once shared |
| Delete (unshared) | Actual delete — removes source and vectors |
| Delete (shared) | **Soft-delete** — hides for the deleting user only; other users still see it |
| Rename | Owner only |

### Groups

| Action | Rule |
|---|---|
| Default visibility | Private (owner only) |
| Share | Owner can share with `read` or `readwrite` permission |
| Unshare | Allowed — other users lose access to the group (but auto-shared child files persist) |
| Delete | Owner only — actual delete |
| Rename | Owner only |
| Add/remove members | Owner, or any user with `readwrite` permission |

**Auto-sharing on group share:** When a group is shared, all child files (recursively) are automatically shared with the same scope. Since files cannot be unshared, this is irreversible. The API provides a `share-preview` endpoint to warn users how many files will be auto-shared.

**Inheritance for new members:** When a file is added to a shared group, it automatically inherits the group's share settings.

### Notes

| Action | Rule |
|---|---|
| Default visibility | Private (session owner only) |
| Share | Session owner can share with `read` or `readwrite` permission |
| Unshare | Allowed |
| Delete | Session owner only |
| Edit | Session owner, or any user with `readwrite` permission |

## Data Model

### `SourceShare` table

One row per shared source (unique constraint on `source_id`).

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `source_id` | FK `sources.id` | The shared source (CASCADE delete) |
| `shared_by` | FK `users.id` | Who shared it (SET NULL on user delete) |
| `scope` | String | `"all"` or `"project"` |
| `project_id` | FK `projects.id` | Required when scope = `"project"` (CASCADE delete) |
| `permission` | String | `"read"` or `"readwrite"` |
| `shared_at` | DateTime | Timestamp of initial share |

### `HiddenSource` table

Tracks per-user soft-deletes for shared files (unique constraint on `user_id` + `source_id`).

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `user_id` | FK `users.id` | The user who hid the source (CASCADE delete) |
| `source_id` | FK `sources.id` | The hidden source (CASCADE delete) |

### Source model additions

- `owner_id` (FK `users.id`, SET NULL) — nullable to handle legacy data and deleted users
- `owner` relationship — eager-loadable for display
- `share` relationship — one-to-one with `SourceShare`

## API Endpoints

### Sharing

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/sources/{id}/share` | Get share info for a source |
| `POST` | `/api/v1/sources/{id}/share` | Share a source |
| `PATCH` | `/api/v1/sources/{id}/share` | Update share scope or permission |
| `DELETE` | `/api/v1/sources/{id}/share` | Unshare a source (400 for files) |
| `GET` | `/api/v1/sources/{id}/share-preview` | Preview auto-share count for groups |

### Share request body

```json
{
  "scope": "all",
  "project_id": null,
  "permission": "read"
}
```

- `scope` — `"all"` or `"project"`
- `project_id` — required when scope is `"project"`
- `permission` — `"read"` or `"readwrite"` (ignored for files, always `"read"`)

### Share response (POST)

```json
{
  "shared": true,
  "auto_shared_files": 3,
  "scope": "all",
  "permission": "read"
}
```

### User profile

| Method | Endpoint | Description |
|---|---|---|
| `PATCH` | `/api/v1/auth/me` | Update display name |

```json
{ "display_name": "Alice" }
```

### Extended source response

`GET /api/v1/sources` and `GET /api/v1/sources/{id}` now include:

```json
{
  "id": "...",
  "type": "file",
  "name": "paper.pdf",
  "owner_id": "user-uuid",
  "owner_name": "Alice",
  "is_shared": true,
  "can_edit": false,
  "share": {
    "shared_by": "user-uuid",
    "shared_by_name": "Alice",
    "scope": "all",
    "project_id": null,
    "permission": "read",
    "shared_at": "2025-01-01T00:00:00Z"
  }
}
```

- `owner_name` — display name (or username) of the source owner
- `is_shared` — whether a share record exists
- `can_edit` — true if the current user is the owner or has `readwrite` permission
- `share` — null when not shared

## Visibility Rules

`GET /api/v1/sources` returns the union of:

1. Sources the user **owns** (via workspace link) that are **not hidden**
2. Sources shared with scope `"all"` that are **not hidden** by this user
3. Sources shared with scope `"project"` where the user is a **member of that project**, and **not hidden**

Admin users follow the same visibility rules (no special bypass).

## Edge Cases

| Scenario | Behavior |
|---|---|
| Owner hides a shared file | Only hidden for that user; others still see it |
| Group unshared | Group disappears for non-owners; auto-shared child files remain shared |
| Project deleted (with project-scoped shares) | FK CASCADE deletes the `SourceShare` rows; those sources revert to private |
| User account deleted | `owner_id` set to NULL; `shared_by` set to NULL; shared sources remain accessible |
| Two users upload the same file (content_hash dedup) | Source keeps original owner; second user gets a workspace link only |
| Readwrite user adds file to shared group | File is owned by the adding user and auto-shared with the group's scope |
| Share scope changed | `PATCH /api/v1/sources/{id}/share` updates the scope/permission in place |

## Frontend

### Share dialog

The share dialog (`ShareDialog` in Sources page) provides:

- Scope selector — radio group: "All users" / "Project members"
- Project dropdown — shown when scope is "project"
- Permission selector — radio: "Read-only" / "Read-write" (for groups and notes)
- Irreversibility warning for files: "Once shared, this file cannot be unshared"
- Group auto-share warning: "This will also share N files in this group"
- For already-shared items: current settings displayed, with unshare button (groups/notes only)

### Visual indicators

- Shared sources show a share icon next to their name
- Sources owned by other users display the owner's name as a suffix
- Tooltip on the share icon shows "Shared by {name}"

### Permission gating in UI

- Only owners see Share / Rename actions
- `readwrite` users can add/remove group members
- `read` users have view-only access
- Delete action wording changes for shared files: "Hide from your view"

### i18n

All sharing-related strings use i18n keys under the `share.*` namespace, with translations for `en-US` and `zh-CN`.

## Database Migration

Migration `d5a3f1e7b9c2_add_sharing_and_ownership`:

- Adds `display_name` column to `users`
- Adds `owner_id` column to `sources` (with FK and index)
- Creates `source_shares` table
- Creates `hidden_sources` table
- Backfills `owner_id` from existing `workspace_sources` links
