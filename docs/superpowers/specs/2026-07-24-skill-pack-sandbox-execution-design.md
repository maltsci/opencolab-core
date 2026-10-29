# Skill-Pack Sandbox Execution Design

## Goal

Let each recommended task run a dedicated, admin-managed **skill pack** inside the codex sandbox. The skill pack contains the instructions (and optional helper scripts) that tell codex how to plan, which tools to call, and what to produce. The outer system (backend) only prepares a per-run workspace: it copies the skill pack in and exports the project's authorized materials as parsed-text files. Planning, tool use, and execution all happen inside the sandbox. Admins upload and manage skill packs; researchers only consume them via recommended tasks.

## User Flow

1. Admin opens **Admin > Skill Packs**, uploads a `.zip` containing a `SKILL.md` at its root.
2. The system validates and stores the pack, then auto-creates (or updates) a recommended task bound to that pack.
3. A researcher selects a project on the Home page and clicks **Use Task** on the task card.
4. A session is created as today; when the task runs, the backend prepares the run workspace and calls the sandbox.
5. Codex reads `SKILL.md`, plans and executes autonomously inside the sandbox, reading `materials/*.md`.
6. The assistant answer (codex's final message) is persisted and rendered in the session, same as the current project-qa path.

## Skill Pack Format

- A `.zip` archive with a `SKILL.md` file at the archive root (not nested in a folder).
- `SKILL.md` starts with YAML front matter:

  ```yaml
  ---
  name: Literature Gap Hunter
  description: Mine contradictions and gaps across the provided materials.
  version: 1
  ---
  ```

  The markdown body below the front matter is the instruction document codex follows. The front-matter `version` is informational only; the database `version` column (auto-incremented per upload) is authoritative.
- Optional extra files (helper scripts, templates, reference data) may sit anywhere in the archive; paths are preserved relative to the pack root.
- Limits: archive ≤ 20 MB, ≤ 200 files, text/script files only (extensions whitelist: `.md .txt .py .sh .json .yaml .yml .csv .j2 .jinja .toml`). No symlinks; no absolute or `..` paths in archive members.

## Backend

### Data model

New table `skill_packs`:

- `id` (str, slugified from front-matter `name` unless the admin overrides; unique)
- `version` (int, monotonically increasing per `id`)
- `name`, `description`
- `storage_path` (str, relative to the skill-pack storage root)
- `is_enabled` (bool, default true)
- `created_by` (user id), `created_at`, `updated_at`

One row per uploaded version; the "current" pack for an id is the highest version. Files live under `<file_storage_root>/skill-packs/{id}/{version}/`, extracted from the uploaded zip. This follows the local-first rule: everything stays on disk locally.

`TaskDefinitionRecord` gains a nullable `skill_pack_id` column. Tasks with `skill_pack_id` set run through the new skill-pack runtime; all existing tasks are untouched.

### Admin API (admin role only, mirroring existing `/admin/skills` patterns)

- `POST /admin/skill-packs` — multipart zip upload. Validates the archive (see format rules), parses front matter, stores files, inserts a new version row, then upserts the bound task (see below). 400 with a precise message on validation failure.
- `GET /admin/skill-packs` — list current versions with their bound task ids.
- `GET /admin/skill-packs/{id}/versions` — version history.
- `PATCH /admin/skill-packs/{id}` — toggle `is_enabled` (also enables/disables the bound task), edit name/description.
- `DELETE /admin/skill-packs/{id}` — removes all versions, stored files, and disables the bound task (task row kept for audit, `is_enabled=false`).

**Task binding**: on upload, upsert a `TaskDefinitionRecord` with id `skill-pack-{skill_pack_id}`, name/description from front matter, `skill_pack_id` set, `result_presentation = {"type": "assistant_message", "runtime": "codex"}`, `project_context_policy = {"inherit_project_sources": true, "include_research_memory": true}`. Re-uploading the same `id` bumps `version` and updates the bound task's name/description.

### Run workspace preparation

New helper in `backend/app/services/skill_pack_service.py`:

```
prepare_skill_run_workspace(run_id, task, session, user, db) -> sandbox_cwd
```

1. Resolve host dir `{codex_runtime_workspace_dir}/skill-runs/{run_id}/` (sibling of the existing `workflow-runs/` layout) and create it.
2. Copy the current skill-pack files into the run dir root (so `./SKILL.md` and helper scripts sit next to `materials/`).
3. Export materials: for every source id from `collect_project_source_ids(db, project_id=session.project_id, user=user)` (existing permission-filtered collection, audit included):
   - Reconstruct the parsed full text from the source's stored chunks (rag_service chunk store), ordered by chunk index. If a source has no chunks, fall back to its `SourceExtraction.structured_json` rendered as markdown; if neither exists, skip it and record a warning.
   - Write `materials/{source_id}.md` with a small header (title, source id).
   - Append `{source_id, title, chunks, status}` to `materials/manifest.json`; skipped sources appear with `status: "skipped"` and a reason.
   - Only parsed text is exported. Original PDFs never enter the workspace.
4. Return the sandbox-side cwd (`{codex_runtime_sandbox_workspace_dir}/skill-runs/{run_id}`).

### Execution path

In the session task-start branch (`Session.tsx` already routes codex tasks; backend side):

- New endpoint `POST /sessions/{session_id}/skill-runs {task_id}` (or extend the existing project-qa orchestration route — pick whichever keeps one obvious path; see Open Decision below).
- Handler: validate the task has an enabled `skill_pack_id`, create an `OrchestrationRun` row (reuse the existing model and status state machine — it already fits: goal, context manifest, final message), call `prepare_skill_run_workspace`, then `run_codex_runtime(prompt=THIN_PROMPT, cwd=sandbox_cwd)`.
- `THIN_PROMPT` is intentionally minimal: "Read ./SKILL.md and follow it exactly to accomplish the user's goal below. Project materials are in ./materials/ (see ./materials/manifest.json). Write your final answer as your last message." plus the user's goal text and, when `include_research_memory` applies, the session research-memory digest (same helper the project-qa path uses).
- On success: persist codex `content` as an assistant `Message`, mark the run completed with `final_message_id`, and store the run context manifest (`skill_pack_id`, `skill_pack_version`, `workspace`) on the run; the per-source materials manifest lives on disk in the run dir. On sandbox failure/timeout: mark the run failed and surface the existing 502/504 semantics.

### What stays unchanged

- Built-in tasks (`project-qa`, `literatures-briefs`, …) and the legacy workflow/agent runtimes.
- The existing JSON `SkillDefinition` admin page (workflow-step skills) — a separate concept; the admin UI labels must distinguish them.
- Sandbox `server.py` — no changes required; it already accepts `cwd` and runs codex in exec mode.

## Frontend

- New admin page `frontend/src/pages/admin/SkillPacks.tsx` following the existing `admin/Skills.tsx` pattern (list + modal/drawer forms), with an Ant Design `Upload` for the zip, enable/disable switch, version list, and delete confirm. Registered under the admin routes and nav next to Skills.
- Admin Skills page: add a subtitle/i18n note clarifying it manages workflow-step skill definitions, distinct from skill packs.
- Home recommended-task cards: no change (bound tasks flow through `GET /tasks` as today).
- Session page: route tasks whose definition has a skill pack to the new run endpoint (the frontend already branches per task; add one branch keyed off `task.skill_pack_id != null` exposed in the `TaskDefinition` schema).
- All new strings via i18n keys in `en-US.json` and `zh-CN.json`.

## Error Handling

- Invalid zip (missing `SKILL.md`, bad front matter, forbidden file types, path traversal, oversize) → 400 with a specific localized message; nothing is persisted.
- Material export failures are per-source: record in the manifest and continue; if zero materials export successfully the run still proceeds (the skill decides how to cope) but the manifest says so.
- Skill pack disabled or deleted while a run is queued → 409 on run creation.
- Sandbox errors keep the current mapping (timeout 504, non-zero exit 502) and mark the orchestration run failed.

## Security & Privacy

- Only parsed text leaves the database into the workspace; original PDFs stay in `uploads/` (unchanged data-privacy rule).
- Material collection goes through the existing permission-filtered `collect_project_source_ids`, so a skill run never sees sources the user may not use.
- Zip extraction guards against path traversal and symlinks; archives are extracted with size/file-count limits before any file is written.
- Skill-pack management endpoints require the admin role, same as existing `/admin/*` routes.

## Testing

- Upload validation: valid pack → 201 + task bound; missing `SKILL.md` → 400; path traversal member → 400; re-upload → version bump + task updated.
- Authorization: non-admin → 403 on all `/admin/skill-packs` routes.
- Workspace preparation: exported `materials/` contains exactly the permission-allowed project sources as parsed text; skipped sources recorded in `manifest.json`; no PDF bytes in the run dir.
- Run path: happy path persists an assistant message and a completed run; sandbox failure marks the run failed; disabled pack → 409.
- Frontend: `npm run build` passes.

## Open Decision (resolve in the implementation plan)

- Run endpoint shape: a new `POST /sessions/{id}/skill-runs` vs. generalizing `POST /sessions/{id}/orchestration-runs/project-qa` into `/orchestration-runs/{kind}`. Default choice: generalize the existing orchestration route (one run model, one status machine), with `project-qa` kept as a kind alias for backward compatibility.
