# Session Project Q&A Recommendation Design

## Goal

Make Project Q&A discoverable from the recommended tasks area of a project-bound
session without changing its existing in-session execution flow.

## Behavior

- When a session has a project, Project Q&A is always shown as the first
  recommended task.
- The task is deduplicated if the configured recommended-task API already
  returns it.
- The existing recommendation limit remains four cards: Project Q&A plus up to
  three other tasks.
- Clicking Project Q&A continues to select the task in the current session.
  The user then enters a concrete question and starts the run from the existing
  composer flow.
- Sessions without a project do not show Project Q&A in recommendations.

## Implementation

- Update the session-page recommendation composition after global and
  project-specific tasks are loaded.
- Reuse the existing Project Q&A task definition and task selection handler.
- Do not add backend APIs, persistence fields, or i18n strings.

## Validation

- Add a focused frontend test if the current test setup covers Session task
  composition; otherwise verify the production frontend build.
- Manually confirm that a project session shows Project Q&A first and that a
  non-project session does not show it.
