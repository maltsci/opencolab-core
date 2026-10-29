# Project Permissions

This document describes how user roles govern access to projects in OpenColab.

## Roles

| Role | Description |
|---|---|
| `admin` | System administrator. Full access to all projects and users. |
| `pi` | Principal Investigator. Can manage all projects. |
| `researcher` | Lab member. Access limited to projects they own or are shared into. |

`admin` and `pi` are collectively referred to as **privileged roles** throughout this document.

---

## Project Visibility

| Role | Projects visible |
|---|---|
| admin / pi | All projects in the system |
| researcher | Only projects where they are a member (owner or shared member) |

Researchers can further filter their view:
- **All** — projects they own plus projects shared with them
- **My projects** — only projects they own

---

## Project Lifecycle

### Create

All authenticated users (admin, pi, researcher) can create projects. The creator is automatically added as the **owner** of the project.

### Read (get / list)

- Admin and PI see all projects.
- Researchers see only their own projects and projects explicitly shared with them.
- Any authenticated user can fetch a single project by ID (`GET /api/v1/projects/{id}`) regardless of membership — this is used for deep-links and cross-project references.

### Update (rename / edit description)

| Role | Can update |
|---|---|
| admin / pi | Any project |
| researcher | Only projects they **own** |

### Archive / Unarchive

Soft-delete a project without destroying data. Archived projects are hidden from the default list view and can be restored.

| Role | Can archive/unarchive |
|---|---|
| admin / pi | Any project |
| researcher | Only projects they **own** |

### Delete

Permanently removes the project and all associated data.

| Role | Can delete |
|---|---|
| admin / pi | Any project |
| researcher | Only projects they **own** |

---

## Member Management

A project's membership list records each user's role within the project: `owner` or `member`.

### Add member (`POST /api/v1/projects/{id}/members`)

| Role | Can add members to |
|---|---|
| admin / pi | Any project |
| researcher | Only projects they **own** |

Researchers who are shared into a project as a `member` (non-owner) cannot add other members.

### Remove member (`DELETE /api/v1/projects/{id}/members/{researcher_id}`)

| Role | Can remove members from |
|---|---|
| admin / pi | Any project |
| researcher | Only projects they **own** |

### Leave project (`DELETE /api/v1/projects/{id}/leave`)

A researcher who is a non-owner member of a project can leave it. Owners cannot leave their own project — they must transfer ownership or delete the project instead.

---

## Batch Operations

Batch operations apply permissions per-project. If the user lacks permission for a specific project in the batch, that project is skipped and returned in the `failed` list; the rest of the batch still proceeds.

| Operation | Endpoint | Who can operate on each project |
|---|---|---|
| Batch archive | `POST /api/v1/projects/batch/archive` | admin / pi: any; researcher: owned only |
| Batch delete | `POST /api/v1/projects/batch/delete` | admin / pi: any; researcher: owned only |
| Batch share | `POST /api/v1/projects/batch/share` | admin / pi: any; researcher: owned only |

---

## Filter Capabilities

### Admin / PI

- **Filter by owner** — multi-select dropdown listing all users who own at least one project (current user listed first)
- **Show archived** — checkbox to include archived projects in the list

### Researcher

- **Scope** — segmented control: "All projects" (own + shared) vs "My projects" (owned only)
- **Show archived** — checkbox to include archived projects in the list

---

## UI Behavior

- The **Members dialog** shows the add-member form and per-member remove button only when the current user has permission to manage members (admin, pi, or project owner).
- Per-project **Archive**, **Delete**, and **Leave** buttons are rendered only when the current user has the corresponding permission.
- The **Owner** tag (blue) is shown on projects the current user owns; otherwise the owner's name is shown in muted text.
- Archived projects are visually dimmed (`opacity: 0.6`) and tagged as **Archived**.

---

## Summary Table

| Action | admin | pi | researcher (owner) | researcher (member) |
|---|:---:|:---:|:---:|:---:|
| Create project | ✓ | ✓ | ✓ | ✓ |
| List all projects | ✓ | ✓ | — | — |
| List own/shared projects | ✓ | ✓ | ✓ | ✓ |
| Get project by ID | ✓ | ✓ | ✓ | ✓ |
| Update project | ✓ | ✓ | ✓ | — |
| Archive / Unarchive | ✓ | ✓ | ✓ | — |
| Delete | ✓ | ✓ | ✓ | — |
| Add member | ✓ | ✓ | ✓ | — |
| Remove member | ✓ | ✓ | ✓ | — |
| Leave project | — | — | — | ✓ |
| Batch archive / delete / share | ✓ | ✓ | ✓ (owned) | — |
