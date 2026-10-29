# OpenColab Research Agents v0 Design

Date: 2026-07-07
Status: Draft approved for planning

## Summary

This design adds two high-priority research agents to OpenColab v0:

- `Literature Synthesizer`
- `Reviewer Assistant`

The implementation route is deliberately lightweight. OpenColab should not introduce a heavyweight workflow framework, autonomous multi-agent debate, or a visual workflow builder in v0. Instead, each agent should run as a deterministic staged pipeline on top of the existing session, source, citation, trace, and LLM-profile infrastructure.

The goal is to complete the missing top-priority v0 requirement while preserving a clean path toward future user-defined skills.

## Product Goal

OpenColab already supports document upload, citation-grounded chat, and replayable answer traces. The missing capability is reusable agent workflows for common research tasks.

The product goal of this iteration is:

> Let a researcher run focused research workflows that produce structured outputs, citations, and replayable traces without requiring them to prompt-engineer every step by hand.

For v0, the agents should feel like guided research operators rather than autonomous coworkers.

## Scope

This iteration must add:

1. A minimal backend agent runtime
2. A persistent `AgentRun` record
3. Two built-in agent definitions
4. Agent run APIs
5. Minimal frontend entry points
6. Trace and citation display for agent outputs

This iteration will not add:

- LangGraph-based orchestration
- multi-agent debate
- arbitrary user-authored Python tools
- visual workflow design
- background distributed execution
- full notebook authoring

## Chosen Technical Route

### Why not a heavy agent framework

The current codebase is still centered on:

- FastAPI APIs
- WebSocket-based chat
- PostgreSQL persistence
- Qdrant retrieval
- LiteLLM-based model calls
- React session/source/admin pages

Introducing LangGraph, CrewAI, or AutoGen for v0 would create more surface area than value:

- more runtime complexity
- harder debugging
- less transparent traces
- more migration work before the product value is proven

The current product need is not open-ended autonomy. The current need is repeatable research workflows with observable steps.

### Chosen runtime shape

Each agent is a deterministic staged pipeline:

1. `retrieve`
2. `synthesize`
3. `validate`
4. `format_output`

Each step records:

- input summary
- output summary
- citations if relevant
- status

The runtime should stay small enough to live inside the current backend service layer.

## Agent Runtime Design

### Core abstractions

#### AgentDefinition

`AgentDefinition` is a code-level definition for a built-in agent.

Fields:

- `name`
- `label`
- `description`
- `input_schema`
- `default_steps`
- `runner`

This does not need to be persisted in v0. Definitions can live in Python modules.

#### AgentRun

`AgentRun` is a persisted record for each invocation.

Fields:

- `id`
- `session_id`
- `user_id`
- `agent_name`
- `status`
- `input_json`
- `steps_json`
- `output_json`
- `error_message`
- `created_at`
- `updated_at`

Status values:

- `pending`
- `running`
- `completed`
- `failed`

#### Step record

Each run stores a compact step record in `steps_json`.

Example:

```json
[
  {
    "name": "retrieve",
    "status": "completed",
    "summary": "retrieved 6 relevant chunks from 3 documents"
  },
  {
    "name": "synthesize",
    "status": "completed",
    "summary": "built cross-paper comparison and disagreement summary"
  },
  {
    "name": "validate",
    "status": "completed",
    "summary": "checked unsupported claims and softened uncertain conclusions"
  },
  {
    "name": "format_output",
    "status": "completed",
    "summary": "generated final structured response"
  }
]
```

### Runtime boundaries

The runtime should reuse existing services wherever possible:

- source selection from sessions
- retrieval from the existing vector store service
- citation building from retrieved chunks
- LLM invocation from the current LLM service and active profile resolution
- trace persistence using the existing trace model pattern

The runtime should not invent a second retrieval stack or a second trace format.

## Built-in Agents

### Literature Synthesizer

#### Purpose

Help a researcher compare a set of selected papers around a question or theme.

#### Inputs

- `query`: required text
- `source_ids`: required list of at least 2 source ids
- `focus`: optional text

#### Output shape

```json
{
  "overview": "short synthesis",
  "consensus": ["..."],
  "differences": ["..."],
  "gaps": ["..."],
  "next_questions": ["..."]
}
```

#### Step behavior

1. `retrieve`
   - retrieve relevant chunks from selected sources
   - group by source
2. `synthesize`
   - compare claims, methods, and takeaways
3. `validate`
   - remove claims not grounded in retrieved evidence
   - mark uncertainty where evidence is weak or conflicting
4. `format_output`
   - produce a structured synthesis response

### Reviewer Assistant

#### Purpose

Help a researcher respond to reviewer comments with grounded strategy and draft language.

#### Inputs

- `review_comments`: required text
- `source_ids`: optional supporting papers or internal notes
- `paper_context`: optional text

#### Output shape

```json
{
  "overall_strategy": "short response strategy",
  "comment_responses": [
    {
      "comment": "...",
      "strategy": "...",
      "draft": "...",
      "evidence_gaps": ["..."]
    }
  ],
  "risks": ["..."]
}
```

#### Step behavior

1. `retrieve`
   - retrieve supporting passages from selected sources
2. `synthesize`
   - map reviewer concerns to evidence and response tactics
3. `validate`
   - identify unsupported rebuttal claims
   - keep tone measured and non-defensive
4. `format_output`
   - produce a per-comment structured response draft

## API Design

### Create run

`POST /api/v1/agents/run`

Request:

```json
{
  "session_id": "session-id",
  "agent": "literature_synthesizer",
  "source_ids": ["source-1", "source-2"],
  "input": {
    "query": "What do these papers disagree on?"
  }
}
```

Response:

```json
{
  "id": "run-id",
  "agent_name": "literature_synthesizer",
  "status": "completed",
  "output": {
    "overview": "...",
    "consensus": [],
    "differences": [],
    "gaps": [],
    "next_questions": []
  },
  "steps": [],
  "trace": {
    "inputs": {},
    "retrieval": [],
    "citations": [],
    "summary_steps": []
  }
}
```

### Get run

`GET /api/v1/agents/runs/{run_id}`

Returns persisted run state, output, and trace payload.

## Data Model Changes

### New model

Add `backend/app/models/agent_run.py` with:

- SQLAlchemy model `AgentRun`
- foreign keys to `sessions` and `users`
- JSON columns for `input_json`, `steps_json`, `output_json`

### Existing trace model

The existing `ResearchTrace` model should be extended carefully to support agent runs.

V0 already anticipates `agent_run_id` in the earlier design, but current implementation only stores session/message-linked traces. This iteration should add optional linkage from `ResearchTrace` to `AgentRun`.

That keeps one trace concept across:

- chat answer traces
- agent output traces

## Frontend Design

### Minimal entry points

Add a simple `Run Agent` entry inside the session page.

V0 interaction:

1. user opens a session
2. user selects sources
3. user clicks `Run Agent`
4. user chooses:
   - Literature Synthesizer
   - Reviewer Assistant
5. user fills the required text input
6. UI submits and renders the structured output

### Presentation

Agent output should appear as a special assistant-style block in the session workspace or a dedicated panel below chat, whichever requires fewer disruptive changes.

V0 should display:

- agent name
- structured output
- citations
- trace steps

### What not to build yet

Do not build:

- a separate workflow canvas
- drag-and-drop step editing
- agent marketplace UI
- nested agent runs inside chat bubbles

## Path Toward User-Defined Skills

The chosen architecture should evolve naturally into user-defined skills.

### v0 built-in shape

In v0, an agent is implemented in code as:

- prompt logic
- input schema
- allowed steps
- formatting rules

### v1 skill shape

In v1, a user-defined skill can be introduced as a persisted configuration:

```json
{
  "name": "paper_compare",
  "label": "Paper Compare",
  "step_template": ["retrieve", "synthesize", "validate", "format_output"],
  "prompt_template": "...",
  "input_schema": {
    "query": "string"
  },
  "output_schema": {
    "overview": "string"
  }
}
```

This means the v0 runtime should avoid hard-coding every behavior deep inside route handlers. The step execution contract should be explicit enough that future skill definitions can reuse it.

### Future skill levels

1. `Prompt Skill`
   - user defines prompt template + output schema
   - runtime reuses retrieval, citation, and trace plumbing
2. `Composable Skill`
   - user chooses a fixed step sequence
   - runtime executes the configured pipeline
3. `Advanced Tool Skill`
   - future, out of v0 scope

This path is only viable if v0 agents are built as runtime-managed pipelines rather than one-off API endpoints with bespoke formatting logic.

## Error Handling

Agent runs should degrade clearly and safely:

- invalid input -> 422 validation error
- fewer than required sources -> clear error
- retrieval returns no useful chunks -> successful run with low-confidence empty-state response
- LLM failure -> failed run + sanitized error message
- trace persistence failure -> run may still complete, but UI should surface missing trace state

Errors must not leak:

- API keys
- provider secrets
- raw stack traces in user-facing payloads

## Testing Expectations

Backend tests should cover:

- agent run request validation
- Literature Synthesizer happy path
- Reviewer Assistant happy path
- step recording order
- trace creation for agent outputs
- workspace isolation
- failure response sanitization

Frontend checks should cover:

- user can open agent modal
- user can submit each built-in agent
- result renders with citations
- trace opens for an agent result

## Rollout Plan

The implementation should proceed in this order:

1. Add `AgentRun` model and migration
2. Add schemas and service-layer runtime
3. Implement Literature Synthesizer
4. Implement Reviewer Assistant
5. Persist traces and citations for runs
6. Add minimal session UI
7. Update README to reflect actual delivered scope

## Decision

OpenColab should implement the two required v0 research agents using a lightweight deterministic runtime layered on the existing RAG and trace system. This route completes the missing v0 requirement, reduces delivery risk, and creates a clean foundation for future user-defined skills without prematurely introducing framework-heavy orchestration.
