# Codex-Guided Research Orchestrator Design

Date: 2026-07-22

Status: Approved for implementation planning

## Summary

OpenColab will add a lightweight, Codex-guided Orchestrator for project-scoped scientific tasks. A researcher selects a task inside a project, provides a goal, and continues the work through a task conversation. The Orchestrator packages governed project context, lets Codex plan and execute an iterative research loop, brokers allowed capabilities through a Tool Gateway, validates results, and persists durable task outputs.

The product model remains:

```text
Project → Task → Task Conversation → Research Memory
```

The execution model becomes:

```text
OpenColab control plane → Codex Sandbox reasoning loop → Tool Gateway → governed capabilities
```

Codex owns the reasoning and planning loop for one run. OpenColab owns authorization, data policy, project context, approval decisions, audit records, artifacts, and long-term research memory.

## Product Decisions

- Use constrained dynamic orchestration. A task defines the allowed Skill/MCP capabilities, context policy, budget, approval policy, and output contract. Codex may only plan inside this boundary.
- Use progressive visibility. Simple project questions return directly; multi-step plans and progress are available in the task workspace; risky actions require explicit approval.
- Persist generated results as versioned task artifacts before publishing them to the project library or research memory.
- Reuse the existing `Session` as the durable task conversation. Every user turn creates an independent `OrchestrationRun` with its own plan and audit record.
- Register MCP servers through administration and expose only task-allowlisted tools through a governed Tool Gateway. Offline deployments disable remote MCP servers.
- Validate the first release through three representative tasks: project Q&A, literature synthesis, and research document drafting.
- Use Codex as the autonomous planner/executor, but never give Codex unrestricted MCP connections, platform credentials, raw PDF access, or ownership of durable state.

## Scope

### In scope

- Task-scoped Codex orchestration runs.
- Dynamic plan creation and revision inside a task-defined capability allowlist.
- A run-scoped Tool Gateway for project retrieval, registered Skills/Workflows, registered MCP tools, and draft artifact operations.
- Project context packaging from approved chunks, research memory, prior task artifacts, and a conversation summary.
- Plan, tool-call, approval, progress, output, and failure persistence.
- Resumable runs after an approval decision.
- Versioned task artifacts with draft and published states.
- Progressive task-workspace UI and real-time run events.
- Initial output contracts for project Q&A, literature synthesis, and research document drafting.

### Out of scope

- Unrestricted shell execution or arbitrary user-supplied tools.
- Direct Codex access to credentials, internal database connections, or raw project PDFs.
- Cross-project task context or cross-project artifact publication.
- Autonomous publication to the project library or research memory.
- A visual workflow builder, general DAG scheduler, marketplace, billing, or distributed worker platform.
- Automatic retry of remote or approval-gated operations.

## Architecture

### Control plane: OpenColab

OpenColab performs the following before and after Codex execution:

1. Authorizes access to the project, task, session, sources, artifacts, and memory.
2. Resolves the task definition and snapshots its capability, context, approval, budget, and output policies.
3. Builds a filtered research context bundle. The bundle may contain extracted text chunks, evidence metadata, research-memory summaries, selected artifact revisions, and conversation summary. It never contains raw PDFs.
4. Creates and owns the `OrchestrationRun`, `ToolInvocation`, approval state, artifact records, messages, and audit events.
5. Issues a short-lived run-scoped Tool Gateway token and an allowlisted tool manifest to the Sandbox.
6. Validates final output against the task output contract, citation policy, and privacy policy.
7. Delivers the final answer and updates the conversation summary.

### Reasoning plane: Codex Sandbox

The existing Codex Sandbox is extended from one opaque prompt execution into a resumable agent session. For one `OrchestrationRun`, Codex:

1. Interprets the user goal and supplied research context.
2. Emits a concise execution plan.
3. Uses only the Tool Gateway capabilities advertised in the run-scoped manifest.
4. Revises the plan in response to tool results or structured errors, within configured call, time, and cost limits.
5. Emits a structured pause envelope when an approval is required.
6. Emits a structured final envelope containing the researcher-facing response, proposed artifact content, citations, and provenance.

The Sandbox must return machine-readable events during execution. OpenColab translates those events into persisted run state and frontend updates. The Sandbox is not a source of truth for any durable scientific state.

### Capability plane: Tool Gateway

The Tool Gateway is the only capability endpoint available to Codex. It is exposed to the Sandbox as a task-scoped MCP-compatible server or equivalent tool protocol.

Gateway adapters include:

- Project retrieval, backed by the existing RAG and access-policy services.
- Existing built-in or installed Skills and fixed Workflows.
- Administrator-registered MCP servers and tools.
- Draft artifact creation and revision.
- Explicit research-memory publication requests.

Every invocation validates the run token, project scope, task allowlist, argument schema, budget, and approval policy before calling an adapter. It creates a `ToolInvocation` record before execution and records only safe, redacted payloads and result summaries.

## Task Definition Extensions

`TaskDefinition` remains the researcher-facing task wrapper. It gains three declarative fields.

```json
{
  "capabilities": {
    "skills": ["rag-retrieve", "literature-synthesize"],
    "mcp_tools": ["local-literature.search", "local-literature.fetch"],
    "artifact_operations": ["create_draft", "revise_draft"]
  },
  "orchestration_policy": {
    "runtime": "codex",
    "max_tool_calls": 12,
    "max_duration_seconds": 900,
    "max_context_chunks": 20,
    "plan_visibility": "progressive",
    "approval_rules": {
      "remote_mcp": "required",
      "publish_artifact": "required",
      "write_research_memory": "required"
    }
  },
  "output_contract": {
    "artifact_type": "report",
    "content_format": "markdown",
    "citation_required": true,
    "required_sections": ["overview", "evidence", "contradictions", "gaps"]
  }
}
```

Existing `workflow_id` remains supported for backwards compatibility. A fixed Workflow is exposed to Codex as one governed capability rather than acting as the primary state machine for a Codex-guided run.

## Persistence Model

### Session extension

Reuse `Session` as the task conversation and add:

- `task_id`: nullable task-definition identifier for task-scoped sessions.
- `conversation_summary`: compact system-generated summary used for future turns.

Existing messages remain the human-readable conversation record. A task session belongs to one project and one task.

### OrchestrationRun

One record represents one user turn and one resumable Codex execution.

- `id`
- `session_id`
- `task_id`
- `turn_index`
- `status`: `planning`, `running`, `waiting_for_approval`, `completed`, `failed`, `cancelled`
- `goal_message_id`
- `plan_snapshot`
- `capability_snapshot`
- `context_manifest`
- `output_contract_snapshot`
- `sandbox_session_id` and encrypted/opaque `resume_token`
- `budget_usage`
- `final_message_id`
- `error_code` and safe `error_message`
- creator and timestamps

Snapshots make runs replayable even when a task definition changes later.

### ToolInvocation

One record represents a request through the Tool Gateway.

- `id`, `orchestration_run_id`, and sequential call number
- capability namespace and identifier
- risk level and status
- redacted request payload and result summary
- approval status, approver, and approval time when applicable
- started/finished timestamps and safe error fields

### TaskArtifact and TaskArtifactRevision

`TaskArtifact` is the stable identity of an answer, report, or document produced in a task session. `TaskArtifactRevision` contains immutable content versions.

- Artifact: `id`, `session_id`, `project_id`, `task_id`, `type` (`answer`, `report`, `document`), `title`, `status` (`draft`, `published`, `archived`), `current_revision_id`, creator, timestamps.
- Revision: `id`, `artifact_id`, revision number, content format (`markdown` or `json`), content, citations/provenance metadata, `orchestration_run_id`, creator, timestamp.

Publishing to the library or research memory is an explicit, approval-gated action. Revisions remain available after later turns modify an artifact.

## Execution Lifecycle

1. The user submits a goal inside a task session.
2. OpenColab creates a user message and `OrchestrationRun`, snapshots the task policies, and builds filtered project context.
3. OpenColab starts or resumes a Codex Sandbox session with the context bundle, tool manifest, short-lived token, and output contract.
4. Codex emits a plan. The UI shows it according to progressive-visibility policy.
5. Codex invokes the Tool Gateway iteratively. The Gateway validates, records, and executes each allowed call.
6. If a call requires approval, the Gateway returns a structured approval requirement. OpenColab marks the run `waiting_for_approval`; Codex returns a pause envelope and resume identity.
7. The user approves or declines. Approval resumes the Codex session; decline returns a structured tool result so Codex can adapt or finish with a partial result.
8. Codex emits final content and artifact proposal. OpenColab validates the output contract, persists an assistant message and draft artifact revision, updates the conversation summary, and completes the run.

If a tool fails, Codex receives a structured error and may re-plan within budget. If the run fails, times out, or is cancelled, completed tool records and draft artifact revisions remain available.

## Governance and Data Privacy

### Capability policy

- Auto-execute: project retrieval, allowlisted local read-only Skills/MCP tools, and draft artifact creation or revision.
- Approval required: remote MCP invocation, artifact publication, research-memory writeback, and operations that exceed a task budget.
- Always deny: unlisted tools, raw PDF export, credentials, arbitrary network calls, direct database access, and cross-project access.

### MCP registry

Administrators register MCP server definitions, authentication configuration, network classification (`local` or `remote`), available tools, and argument schemas. Secrets remain encrypted in platform configuration and are never included in Codex context or tool manifests. The Tool Gateway uses the configured connection on Codex's behalf.

Offline mode hides remote MCP capabilities entirely.

### Context policy

Raw uploaded data and PDFs never leave the local processing boundary. The context bundle contains only policy-approved extracted text segments, embeddings-derived retrieval results, metadata, and derived research memory. Cloud-backed Codex/LLM use requires the existing hybrid-mode consent and receives only these approved segments.

## User Experience

The existing `TaskWorkspace` evolves in place:

- The main pane remains a task conversation and composer.
- A project-context indicator shows selected documents, research memory, and prior artifacts.
- A compact plan card appears for multi-step runs, with optional step detail and live progress.
- A right-side status area shows current run, approval requests, budget state, and active artifact.
- Navigation exposes conversation, artifacts, run history, and project sources.
- Completed reports and documents render as draft artifacts with revision history, citation status, download, continue-editing, and publish actions.

Simple project Q&A returns a citation-grounded answer with minimal execution detail. Literature synthesis creates a structured report. Research document drafting creates a versioned Markdown document that later turns can revise.

## API and Event Surface

The exact route names may follow existing API conventions, but the capability surface is:

- Create, read, cancel, and resume orchestration runs under a session.
- Subscribe to run events through WebSocket or Server-Sent Events.
- Read the plan, ToolInvocations, and audit-safe event history for a run.
- Submit approval decisions for pending invocations.
- Create, read, revise, and publish task artifacts.
- Expose a run-scoped Tool Gateway endpoint to Codex.

Run events include `plan_created`, `plan_updated`, `tool_requested`, `tool_completed`, `approval_required`, `approval_resolved`, `artifact_revision_created`, `finalized`, and `failed`.

## Error Handling

- Validate task and project access before creating a run.
- Reject tool calls with expired tokens, missing scopes, invalid schemas, exhausted budgets, or unavailable MCP servers.
- Return structured safe errors to Codex so it can adapt; never include credentials or raw internal exceptions.
- Persist a partial result or draft artifact when valid completed work exists.
- Do not auto-retry remote or approval-gated operations.
- Mark output-contract validation failures clearly and keep the artifact in draft state.

## Acceptance Criteria

1. A researcher can run project Q&A, literature synthesis, and document drafting inside a project task workspace.
2. Each user turn creates a separately inspectable, resumable `OrchestrationRun` and inherits task conversation summary, approved context, and active artifacts.
3. Codex cannot enumerate or invoke a Skill/MCP capability outside the task allowlist.
4. Every Tool Gateway call records an auditable, redacted `ToolInvocation` linked to the run, user, and project.
5. Remote MCP, publication, and research-memory writeback pause for approval; approving or declining resumes the run deterministically.
6. Document and report outputs create versioned draft artifacts and can be published only through explicit approval.
7. Existing fixed Workflow tasks and current TaskWorkspace behavior remain functional.
8. Raw PDFs and credentials are absent from Sandbox context and remote tool payloads.
9. Unit and API tests cover policy enforcement, lifecycle persistence, approval/resume, artifact revisioning, context filtering, and the three task contracts.
