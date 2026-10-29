# Project Q&A Session Launch and Shared Context Design

## Goal

Make Project Q&A start from the standard conversation page and reliably use all authorized, searchable documents attached to the project, including documents nested inside project source groups.

## Entry Flow

The home page remains the project and task discovery surface. Selecting Project Q&A creates a new session with the selected `project_id` and `task_id=project-qa`, then opens the normal session route. The first submitted question starts the Project Q&A orchestration run; the task workbench's separate save-and-continue step is not used for this entry.

## Shared Project Context

Project Q&A resolves active project assets to source IDs, expands any source groups to their child documents, and then applies the existing agent-use permission checks. A project link to a source group explicitly synchronizes a project link for each current leaf document; it does not bypass the leaf document's access policy. When a member is later added to or removed from a project-linked group, its project link is added or removed by the same synchronization path. Only child sources with searchable chunks are supplied to the Codex runtime. Research objects without a `source_id` remain project memory, not document retrieval sources.

## Conversation Visibility

The project-Q&A session page shows a compact context panel with the inherited source groups, resolved documents, searchable chunk count, and excluded assets with a reason. This makes automatic project sharing auditable without asking users to link the same document per session.

## Compatibility

The existing `/projects/:projectId/tasks/:taskId` workbench remains unchanged for all current workflow tasks. Project Q&A gains a standard-session entry path only; the existing orchestration run API remains the execution boundary. Existing project-linked source groups are synchronized on demand by the Project Q&A context resolver, allowing legacy groups such as 医疗项目/抗菌肽 to acquire auditable leaf-document project links before execution.

## Validation

- API tests cover source-group expansion and context manifest contents.
- API tests cover a Project Q&A session created from the home entry.
- Frontend build passes and a browser smoke test verifies direct navigation, context visibility, and a completed answer.
