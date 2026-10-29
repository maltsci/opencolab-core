# OpenColab Skill + Workflow Runtime v1 Design

Date: 2026-07-13
Status: Draft approved for planning

## Summary

This design evolves OpenColab from the current lightweight research-agent model into a research-memory-centered skill and workflow runtime.

The current agent shape is:

```text
Agent = prompt + retrieval + output
```

The target v1 shape is:

```text
Skill = reusable research capability
Workflow = ordered multi-step execution plan
Runtime = execution, validation, trace, and memory writeback
Research Memory = durable scientific state
Agent = preset workflow + UI entry point + domain policy
```

The core product decision is that OpenColab should not become a generic agent platform first and then retrofit scientific abstractions later. OpenColab should keep scientific objects, relations, evidence, workflow state, permissions, and auditability in its own platform layer. Delegated runtimes, including a future Codex sandbox integration, may execute work, but they should not own the platform's long-term research state.

## Product Goal

OpenColab already has:

- document-grounded chat
- two built-in research agents
- persisted `AgentRun` records
- replayable traces
- session-scoped `ResearchObject` records
- `ResearchObjectRelation` records with evidence payloads
- an agent output save flow into research memory

The missing next layer is:

> Let repeatable research capabilities become explicit skills and workflows, so their execution can be traced step by step and their outputs can be written back into durable research memory.

This should make the existing agents less like one-off service functions and more like registered product capabilities that can later be composed, versioned, validated, and governed.

## Scope

### In scope for v1

- Add declarative built-in `SkillDefinition` records in code or bundled YAML/JSON.
- Add declarative built-in `WorkflowDefinition` records in code or bundled YAML/JSON.
- Add a skill registry that can list and resolve built-in skills.
- Add a workflow registry that can list and resolve built-in workflows.
- Add persistent `WorkflowRun` records.
- Add persistent `StepRun` records.
- Migrate the existing `literature_synthesizer` and `reviewer_assistant` behaviors into built-in workflows.
- Preserve the existing `/api/v1/agents` API as a compatibility layer.
- Add first-class workflow APIs for listing workflows, starting runs, reading runs, and reading step runs.
- Reuse existing RAG, LLM, citation, trace, and research-memory services.
- Keep research memory writeback in the platform layer.
- Define a future delegated-runtime boundary for Codex sandbox without implementing it in v1.

### Out of scope for v1

- User-authored arbitrary Python execution.
- User-installed external tools.
- Arbitrary shell execution.
- Multi-agent autonomous planning.
- Complex DAG scheduling.
- Background distributed workers beyond the existing backend execution path.
- Visual workflow builder.
- Skill marketplace.
- Cross-project research-memory linking.
- SaaS-grade tenant isolation, billing, or per-tool cost accounting.
- Codex sandbox execution integration.

## Architectural Position

### Platform-owned core state

OpenColab must own the durable scientific state:

- `ResearchObject`
- `ResearchObjectRelation`
- evidence payloads
- citations and traces
- `WorkflowDefinition`
- `WorkflowRun`
- `StepRun`
- permissions
- audit-relevant creator fields

These are platform abstractions, not delegated-runtime abstractions.

### Runtime-owned execution

The runtime executes declared steps and records outcomes. In v1 it should remain intentionally narrow:

- resolve workflow definition
- validate input payload
- create a `WorkflowRun`
- execute steps in dependency order
- create one `StepRun` per step
- call existing services for retrieval, LLM, formatting, validation, and memory writeback
- mark statuses and persist errors

### Agent as product wrapper

In v1, agents should no longer be the lowest-level execution primitive.

An agent should be treated as:

```text
Agent = workflow_id + UI entry point + domain-specific labels/policy
```

For compatibility, the existing `AgentRun` API can remain, but internally it should delegate to the workflow runtime.

## Core Abstractions

### SkillDefinition

A skill is a reusable, controlled research capability. In v1, skills are built in and registered by the backend. They are not user-editable.

Minimum fields:

- `id`
- `version`
- `name`
- `description`
- `input_schema`
- `output_schema`
- `tools`
- `step_template`
- `validation_rules`
- `writeback_policy`

Example built-in skills:

- `rag-retrieve`
- `literature-synthesize`
- `grounding-validate`
- `review-response-draft`
- `memory-writeback`

### WorkflowDefinition

A workflow composes skills, LLM calls, tools, and optional human checkpoints into a repeatable execution path.

Minimum fields:

- `id`
- `version`
- `name`
- `description`
- `input_schema`
- `steps`
- `checkpoint_policy`
- `writeback_policy`

Each step contains:

- `id`
- `type`: `skill`, `llm`, `tool`, or `human_checkpoint`
- `ref`
- `depends_on`
- `retry_policy`
- `validation_rule`
- `output_key`

For v1, `depends_on` should be accepted but only simple linear workflows need to be executed. This keeps the schema forward-compatible without requiring a general DAG scheduler immediately.

### WorkflowRun

A `WorkflowRun` is one invocation of a workflow.

Fields:

- `id`
- `workflow_id`
- `workflow_version`
- `session_id`
- `status`
- `input_payload`
- `output_payload`
- `error_message`
- `started_at`
- `finished_at`
- `created_by`
- `created_by_type`
- `created_at`
- `updated_at`

Initial statuses:

- `pending`
- `running`
- `waiting_for_checkpoint`
- `completed`
- `failed`
- `cancelled`

`waiting_for_checkpoint` is included for schema stability, but v1 does not need a full checkpoint UI.

### StepRun

A `StepRun` is one executed step inside a workflow run.

Fields:

- `id`
- `workflow_run_id`
- `step_id`
- `step_type`
- `ref`
- `status`
- `input_payload`
- `output_payload`
- `error_message`
- `attempt_count`
- `started_at`
- `finished_at`
- `created_at`
- `updated_at`

Initial statuses:

- `pending`
- `running`
- `completed`
- `failed`
- `skipped`
- `waiting_for_checkpoint`

### SkillRun

v1 should not add a separate `SkillRun` table.

Instead:

```text
StepRun(step_type = "skill")
```

is sufficient for traceability. A separate `SkillRun` can be introduced later if a skill needs nested execution state, detailed cost tracking, or reusable run-level audit metadata.

## Declarative Definition Shape

The backend can start with Python dictionaries or bundled YAML/JSON files. The important requirement is that definitions are data-shaped and registry-driven, not scattered as special-case service functions.

Example:

```yaml
id: literature-synthesizer
version: 1
name: Literature Synthesizer
description: Summarize selected literature and identify consensus, differences, and gaps.
input_schema:
  type: object
  required:
    - query
    - source_ids
  properties:
    query:
      type: string
    source_ids:
      type: array
      items:
        type: string
    focus:
      type: string
steps:
  - id: retrieve
    type: skill
    ref: rag-retrieve
    output_key: retrieved_chunks
  - id: synthesize
    type: skill
    ref: literature-synthesize
    depends_on:
      - retrieve
    output_key: synthesis
  - id: validate
    type: skill
    ref: grounding-validate
    depends_on:
      - synthesize
    output_key: validation
  - id: format_output
    type: tool
    ref: format-literature-synthesis
    depends_on:
      - validate
    output_key: final_output
output_schema:
  type: object
writeback_policy:
  allowed_object_types:
    - discussion
    - hypothesis
  default_object_type: discussion
  require_user_confirmation: true
```

## Built-in v1 Workflows

### Literature Synthesizer Workflow

Workflow id:

```text
literature-synthesizer
```

Inputs:

- `query`: required string
- `source_ids`: required list with at least two sources
- `focus`: optional string

Steps:

1. `retrieve`
   - use existing RAG retrieval and source expansion
   - output retrieved chunks and citation candidates
2. `synthesize`
   - compare claims, methods, conclusions, and disagreements
   - output structured synthesis
3. `validate`
   - check unsupported claims against retrieved evidence
   - soften uncertain conclusions
4. `format_output`
   - produce the current response shape expected by the frontend

Output:

- `overview`
- `consensus`
- `differences`
- `gaps`
- `next_questions`
- citation payload
- trace summary

### Reviewer Assistant Workflow

Workflow id:

```text
reviewer-assistant
```

Inputs:

- `review_comments`: required string
- `source_ids`: optional list
- `paper_context`: optional string

Steps:

1. `parse_comments`
   - split reviewer input into addressable comment units
2. `retrieve`
   - retrieve supporting evidence when sources are selected
3. `draft_strategy`
   - produce response strategy and risk notes
4. `draft_response`
   - produce draft language for each reviewer comment
5. `validate`
   - flag unsupported claims and missing evidence
6. `format_output`
   - produce the current response shape expected by the frontend

Output:

- `overall_strategy`
- `comment_responses`
- `risks`
- citation payload
- trace summary

## Backend File Structure

Recommended v1 additions:

```text
backend/app/
  skills/
    __init__.py
    registry.py
    schemas.py
    builtin.py
  workflows/
    __init__.py
    registry.py
    schemas.py
    engine.py
    executor.py
    models.py
    policies.py
  runtime/
    __init__.py
    step_runner.py
    validators.py
  memory/
    __init__.py
    writeback.py
```

The exact file split can follow implementation pressure, but the responsibility boundaries should remain:

- `skills`: definition and skill resolution
- `workflows`: workflow definitions, models, and execution orchestration
- `runtime`: step execution helpers and validation
- `memory`: writeback policy and relation/evidence construction

Existing modules should be reused:

- `backend/app/services/rag_service.py`
- `backend/app/services/llm_service.py`
- `backend/app/services/trace_service.py`
- `backend/app/services/agent_runtime.py`
- `backend/app/api/agents.py`
- `backend/app/models/agent_run.py`
- `backend/app/models/research_object.py`

## Data Model

### New table: `workflow_runs`

Recommended columns:

- `id`
- `workflow_id`
- `workflow_version`
- `session_id`
- `status`
- `input_payload`
- `output_payload`
- `error_message`
- `started_at`
- `finished_at`
- `created_by`
- `created_by_type`
- `created_at`
- `updated_at`

Indexes:

- `session_id`
- `workflow_id`
- `status`
- `created_by`

### New table: `step_runs`

Recommended columns:

- `id`
- `workflow_run_id`
- `step_id`
- `step_type`
- `ref`
- `status`
- `input_payload`
- `output_payload`
- `error_message`
- `attempt_count`
- `started_at`
- `finished_at`
- `created_at`
- `updated_at`

Indexes:

- `workflow_run_id`
- `step_id`
- `status`

### Existing table: `agent_runs`

The existing `agent_runs` table should remain in v1.

Recommended migration path:

- add nullable `workflow_run_id` to `agent_runs`
- keep existing `steps_json` and `output_json` for API compatibility
- populate `workflow_run_id` for new agent invocations
- build `AgentRunResponse.steps` from `StepRun` when available
- fall back to `steps_json` for old rows

This avoids breaking current API consumers while making workflow runtime the new source of execution truth.

## API Design

### Skills

```text
GET /api/v1/skills
GET /api/v1/skills/{id}
```

`POST`, `PATCH`, and `DELETE` should not be exposed in v1 because skills are built in.

### Workflows

```text
GET /api/v1/workflows
GET /api/v1/workflows/{id}
POST /api/v1/workflows/{id}/run
```

Start-run request:

```json
{
  "session_id": "session-123",
  "input": {
    "query": "What does the literature say about peptide stability?",
    "source_ids": ["source-a", "source-b"]
  }
}
```

Start-run response:

```json
{
  "id": "workflow-run-123",
  "workflow_id": "literature-synthesizer",
  "status": "completed",
  "output": {
    "overview": "..."
  }
}
```

### Runs

```text
GET /api/v1/workflow-runs/{id}
GET /api/v1/workflow-runs/{id}/steps
POST /api/v1/workflow-runs/{id}/cancel
```

`resume` can wait until checkpoint support is implemented.

### Memory writeback

The existing agent endpoint:

```text
POST /api/v1/agents/runs/{run_id}/save-memory
```

should remain.

Add workflow-native equivalent:

```text
POST /api/v1/workflow-runs/{run_id}/save-memory
```

The behavior should mirror the existing agent memory writeback:

1. verify the workflow run belongs to the current user and session
2. verify the workflow completed successfully
3. create a `ResearchObject`
4. optionally create one `ResearchObjectRelation`
5. populate evidence from trace and citations
6. return the created memory objects

## Execution Flow

### Start workflow

1. User starts a built-in workflow from the UI or compatibility agent API.
2. Backend resolves `WorkflowDefinition`.
3. Backend validates `session_id`, permissions, selected sources, and input payload.
4. Backend creates `WorkflowRun(status = "running")`.
5. Backend creates `StepRun(status = "pending")` records for each workflow step.

### Execute steps

1. Runtime selects the next executable step.
2. Runtime builds step input from:
   - workflow input
   - previous step outputs
   - session context
   - selected sources
3. Runtime marks the step as `running`.
4. Runtime invokes the referenced skill/tool/LLM adapter.
5. Runtime stores step output and status.
6. Runtime records trace and citation payloads where relevant.
7. Runtime continues until all required steps complete or one step fails.

### Complete workflow

1. Runtime builds `WorkflowRun.output_payload` from declared `output_key` values.
2. Runtime marks the run as `completed`.
3. Compatibility layer updates `AgentRun.output_json` and `AgentRun.steps_json` when invoked through the existing agent API.
4. UI renders the output using the existing agent result components at first.

### Fail workflow

1. Runtime marks the failed step as `failed`.
2. Runtime writes a concise internal `error_message`.
3. Runtime marks the workflow run as `failed`.
4. API returns a stable user-facing failure message.
5. Logs preserve enough detail for debugging without exposing secrets.

## Memory Writeback Model

Workflow outputs should not silently become research memory in v1. The writeback policy should keep user confirmation as the default.

Default writeback policy:

- `require_user_confirmation: true`
- allowed object types are declared per workflow
- relation creation is optional
- created relation evidence includes trace id and citations when available

Research object content should include:

- `origin = "workflow_run"`
- `workflow_run_id`
- `agent_run_id` when invoked through agent compatibility API
- `trace_id`
- `source_ids`
- selected workflow output

Relation evidence should follow the existing normalized shape:

```json
{
  "confidence": 0.8,
  "evidence": {
    "trace_id": "trace-123",
    "citations": [],
    "note": "Optional user note"
  }
}
```

## Frontend Shape

v1 should keep the UI practical:

- existing agent entry points continue to work
- agent result cards can be backed by `WorkflowRun` under the hood
- add a simple workflow run detail view or panel when needed
- show step runs as a vertical trace list
- keep memory save UX close to the existing agent save modal

Suggested additions:

```text
frontend/src/
  components/workflows/
    WorkflowRunSteps.tsx
    WorkflowRunStatus.tsx
  components/skills/
    SkillSummary.tsx
```

Admin skill/workflow editing pages should wait until v1.5 or v2.

## Codex Sandbox Boundary

Codex sandbox is valuable as a future delegated runtime, especially for a local team edition where:

- users are few
- environment is trusted
- workloads involve papers, tables, PDFs, Python analysis, and report generation
- concurrency is low

However, Codex sandbox should not own OpenColab's research platform core.

Future delegated runtime responsibilities:

- coding worker
- file/document worker
- script execution worker
- data analysis worker
- skill execution worker
- artifact generation worker

Platform-owned responsibilities:

- `ResearchObject`
- `Hypothesis`
- `Evidence`
- `Relation`
- `Experiment`
- `Workflow`
- `Memory`
- `Permission`
- `Audit`

The future integration contract should look more like:

```text
OpenColab platform:
  create WorkflowRun
  create StepRun
  prepare step input
  grant scoped files/tools
  call delegated runtime
  receive artifacts and structured output
  validate output
  write back memory

Delegated runtime:
  run_step
  run_python
  run_shell
  produce_artifacts
  summarize_process
```

This preserves the early value of a thick local worker while keeping scientific memory and workflow state inside OpenColab.

## Implementation Milestones

### v1

1. Add `WorkflowRun` and `StepRun` models and migration.
2. Add skill and workflow schemas.
3. Add built-in registries.
4. Port existing literature synthesizer into a built-in workflow.
5. Port existing reviewer assistant into a built-in workflow.
6. Add workflow run APIs.
7. Make existing agent API delegate to workflow runtime.
8. Add workflow-native memory save API.
9. Add tests for run creation, step persistence, failure handling, and memory writeback.

### v1.5

1. Add checkpoint persistence and resume API.
2. Add retry policy support.
3. Add validation rule execution.
4. Add UI for step-run inspection.
5. Add admin read-only skill and workflow list pages.
6. Add workflow definition version display.

### v2

1. Add user-defined workflow authoring with strict allowlists.
2. Add lab-internal skill library.
3. Split `Evidence` into first-class table if relation payloads become too large.
4. Add graph-aware reasoning over research memory.
5. Add delegated runtime adapters, including Codex sandbox, behind explicit permissions.

## Risks and Guardrails

### Risk: building a generic workflow engine too early

Guardrail:

- execute only simple linear workflows in v1
- keep `depends_on` schema for future compatibility
- avoid visual workflow authoring

### Risk: losing research state in runtime logs

Guardrail:

- write durable scientific state into `ResearchObject` and `ResearchObjectRelation`
- keep workflow and step state in the database
- treat traces as evidence, not as the only source of memory

### Risk: duplicating current agent logic

Guardrail:

- make the existing agent API a compatibility wrapper
- move shared execution behavior into workflow runtime
- keep old `AgentRun` fields readable for historical rows

### Risk: unsafe arbitrary execution

Guardrail:

- no arbitrary Python, shell, or user-installed tools in v1
- keep all built-in skill refs allowlisted
- define delegated runtime boundary before implementing it

## Success Criteria

The v1 implementation is successful when:

- existing Literature Synthesizer behavior still works through the agent API
- existing Reviewer Assistant behavior still works through the agent API
- each new agent invocation creates a `WorkflowRun`
- each declared step creates a `StepRun`
- workflow run status accurately reflects success or failure
- workflow output can be saved to research memory
- relation evidence continues to include trace and citation payloads
- old `AgentRun` rows remain readable
- tests cover successful runs, failed steps, compatibility response shape, and memory writeback

## One-Sentence Direction

OpenColab should become a research-memory-centered skill and workflow runtime: platform-owned scientific state first, delegated execution second.
