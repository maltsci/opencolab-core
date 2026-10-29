# Project-Exclusive Upload Design

## Goal

Add upload entries to both project assets and session detail pages. Files uploaded from either entry remain exclusive to the current project by default. Session uploads are also attached to the current session so they are available as immediate conversation context. A project member can later publish the material to the lab library as either lab public or lab private.

## User Flow

1. On a project assets page, the user selects **Upload Material**.
2. The user selects one or more supported files.
3. Each uploaded file is materialized as a project-origin asset and linked to the current project.
4. The assets table identifies the material as **Project Upload**.
5. The user may later select **Publish to Lab** for a project-origin asset and choose either lab public or lab private.
6. Publishing keeps the original project association. Lab-private publishing exposes catalog metadata only to other users until access is approved.

## Session Flow

1. On a session detail page, the user selects **Upload Material**.
2. The system uploads the file as a project-origin asset, links it to the session project, and attaches its source to the current session.
3. The user can select **Link Material** to add existing context to the session.
4. The selection dialog groups eligible materials into lab public materials, the user's own materials, and current-project materials not already attached to the session.
5. The system prevents duplicate source attachments to the same session.
6. Lab-private materials are excluded from the default selection dialog. They must first be approved and linked through the library access-request workflow; then they appear in the current-project group.

## Backend

- Add a project-scoped upload endpoint that validates project membership before accepting a file.
- Reuse the existing source ingestion, duplicate detection, materialization, and processing workflow.
- Materialize each upload with `visibility_scope="project"`, `origin_project_id` set to the route project, and a project asset link.
- Do not publish the uploaded material to the lab library during upload.
- Keep the existing lab publication endpoint as the only path that changes the asset to `lab_public` or `lab_private`.
- Reuse the existing session-source attachment API for session uploads and linking existing project materials.
- Restrict session material discovery to lab public assets, user-owned assets, and project-linked assets for the session's project, subject to existing content permissions.

## Frontend

- Add an **Upload Material** button to the project assets page header.
- Use the existing supported-file list and duplicate-upload handling patterns from the library page.
- Show upload progress on the button and refresh the project asset list after completion.
- Keep the existing source tag and project-origin explanation: project-origin assets cannot be unlinked, but can be published to the lab.
- Add **Upload Material** and **Link Material** controls to session detail pages.
- Refresh the session attachment list after a successful upload or link.

## Error Handling

- Surface duplicate-upload results through the existing duplicate dialog.
- Display the backend error detail or the existing localized upload failure message.
- Leave the project assets list unchanged if an upload fails.

## Verification

- Backend test: a project member upload creates a project-origin asset, source, and project link with project visibility.
- Backend test: a user without project access cannot upload to that project.
- Backend test: a session upload creates a project-origin asset and attaches the source to the current session.
- Backend test: eligible session linking includes lab public, user-owned, and project-only materials while excluding duplicate attachments and unapproved lab-private materials.
- Frontend build passes.
