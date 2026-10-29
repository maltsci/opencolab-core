# OpenColab v0 LRAR Design

Date: 2026-06-26
Status: Draft approved for planning

## Summary

OpenColab v0 defines the project as a Local Research AI Runtime (LRAR): a lab-local runtime for research knowledge, AI assistance, and lightweight computation. The v0 goal is not to rebuild the stack or chase a broad multi-agent platform. The goal is to evolve the current working OpenColab codebase from local document RAG chat into a traceable research workspace that scientists can use in a real lab within 2-4 weeks.

The chosen implementation route is incremental:

- Keep the existing FastAPI backend, React/Vite frontend, PostgreSQL database, Qdrant vector store, and document worker.
- Add structured extraction on top of the existing ingestion pipeline.
- Turn chat sessions into research threads with citations and replayable traces.
- Add two simple research agents implemented as deterministic staged pipelines with knowledge-base access.
- Defer framework-heavy workflow orchestration, Next.js migration, pgvector migration, and secure compute sandboxing beyond v0.

## Product Definition

OpenColab v0 is a local-first research assistant runtime for laboratories. It helps researchers upload papers and lab documents, ask citation-grounded questions, synthesize literature, respond to review comments, and replay how a research answer was produced.

The product thesis is:

> OpenColab should make AI part of the research decision process, not just a text generation tool.

The v0 differentiator is not generic RAG, agent branding, or UI polish. The differentiator is a replayable research decision record:

- What documents were used?
- What chunks or extracted claims supported the answer?
- What citations were attached?
- What reasoning or processing steps happened?

OpenColab is not a chat tool. It is a research iteration loop system:

```text
Upload paper
  -> Ask question
  -> AI answers with citations
  -> Save research thread
  -> Reuse the thread in the next question
  -> Agent synthesizes evidence
  -> New hypothesis emerges
  -> New upload or experiment continues the loop
```

The core product loop is deliberately simple. Each cycle should make the next research action easier and better grounded than the previous one.

## Current Baseline

The current repository already provides a useful base:

- `backend/`: FastAPI API service with auth, projects, sessions, sources, messages, notes, tags, admin settings, and WebSocket chat.
- `backend/app/worker/main.py`: document worker that polls pending sources, parses PDFs, chunks text, embeds chunks, and upserts vectors.
- `frontend/`: React + Vite + Ant Design client with login, home, sources, session chat, and admin pages.
- `postgres`: primary relational database.
- `qdrant`: vector search store.
- `LiteLLM`: unified LLM gateway for OpenAI-compatible APIs and local models.

The current implementation is best described as a local-first document RAG chat system. It does not yet implement real multi-agent workflow orchestration, LangGraph, MCP tool execution, PI-led governance, or research workflow checkpoints.

## V0 Scope

V0 must do three things well:

1. Upload PDFs and produce citation-grounded AI answers.
2. Convert each chat session into a replayable research thread.
3. Provide two useful research agents:
   - Literature Synthesizer
   - Reviewer Assistant

V0 should be usable by a small lab with local documents and a configured local or cloud LLM endpoint.

## Non-Goals

V0 will not include:

- LangGraph, AutoGen, CrewAI, or other full agent workflow frameworks.
- Multi-agent autonomous debate or self-directed research loops.
- Next.js migration.
- pgvector migration from Qdrant.
- GPU cluster execution or Ray.
- Fully secure arbitrary code execution.
- Complete paper auto-generation from scratch.
- Wet-lab automation, instrument control, or LIMS integration.
- Full citation graph search across external academic databases.

These remain future milestones after the v0 research thread foundation is stable.

## Architecture

V0 keeps the existing system shape and adds research-runtime capabilities inside the current backend and frontend.

```text
Client: React Research UI
  - Chat workspace
  - Knowledge base upload/search/view
  - Citation and trace panels
  - Lightweight notebook timeline
        |
        | HTTP / WebSocket
        v
API: FastAPI Gateway
  - Auth and project/session routing
  - Source and KB APIs
  - Chat WebSocket
  - Agent run APIs
  - Trace APIs
        |
        +------------------+------------------+
        |                  |                  |
        v                  v                  v
Knowledge Base       Agent Runtime       Compute API Stub
  - PDF ingestion      - fixed stages       - job model first
  - chunks             - KB access          - sandbox later
  - extraction         - citations
  - retrieval
        |
        +------------------+------------------+
                           |
                           v
                 PostgreSQL + Qdrant
```

## Backend Module Changes

Add new modules under the existing `backend/app` tree.

```text
backend/app/
├── api/
│   ├── agents.py
│   ├── compute.py
│   └── research_threads.py
├── models/
│   ├── agent_run.py
│   ├── extraction.py
│   ├── research_object.py
│   └── trace.py
├── schemas/
│   ├── agent.py
│   ├── extraction.py
│   ├── research_object.py
│   └── trace.py
├── services/
│   ├── citation_service.py
│   ├── extraction_service.py
│   ├── trace_service.py
│   └── agents/
│       ├── base.py
│       ├── literature_synthesizer.py
│       └── reviewer_assistant.py
```

Existing modules should remain in place. The current `sessions` and `messages` models become the first implementation of research threads rather than being replaced.

## Data Model Draft

### Document Extraction

`DocumentExtraction` stores structured research content extracted from a source.

Fields:

- `id`
- `source_id`
- `schema_version`
- `document_type`
- `structured_json`
- `status`
- `error_message`
- `created_at`
- `updated_at`

Example `structured_json`:

```json
{
  "type": "paper",
  "title": "Example title",
  "claims": [
    {
      "statement": "The proposed method improves accuracy.",
      "evidence": "Table 2 reports a 3.2 percentage point improvement.",
      "confidence": 0.78,
      "chunk_ids": ["chunk-id-1"]
    }
  ],
  "methods": ["CNN", "data augmentation"],
  "limitations": ["small dataset"],
  "datasets": ["example dataset"],
  "metrics": ["accuracy"]
}
```

The extraction should be stored as JSON for speed of iteration. Strongly typed claim/evidence tables can be added later if queries require them.

### Research Object

`ResearchObject` is the minimal abstraction that lets OpenColab move beyond chat transcripts. It represents reusable research artifacts created by uploads, conversations, agent runs, or future experiments.

Fields:

- `id`
- `type`
- `title`
- `content`
- `content_json`
- `created_by`
- `created_at`
- `updated_at`

Allowed v0 types:

- `paper`
- `experiment`
- `discussion`
- `hypothesis`

Relations are stored separately or in a compact JSON field for v0:

```json
{
  "relations": [
    {
      "type": "cites",
      "target_id": "paper-object-id"
    },
    {
      "type": "supports",
      "target_id": "hypothesis-object-id"
    },
    {
      "type": "contradicts",
      "target_id": "hypothesis-object-id"
    }
  ]
}
```

V0 only needs the relation types `cites`, `supports`, and `contradicts`. This keeps the model small while creating a foundation for a future claim-evidence graph.

### Research Trace

`ResearchTrace` records the replayable parts of a message or agent run. V0 keeps this intentionally small and user-facing.

Fields:

- `id`
- `session_id`
- `message_id`
- `agent_run_id`
- `user_id`
- `inputs_json`
- `retrieval_json`
- `citations_json`
- `summary_steps_json`
- `created_at`

V0 trace payload:

```json
{
  "inputs": {
    "query": "What research gaps do these papers leave open?",
    "source_ids": ["source-id-1", "source-id-2"]
  },
  "retrieval": [
    {
      "source_id": "source-id-1",
      "chunk_id": "chunk-id-1",
      "score": 0.82
    }
  ],
  "citations": [
    {
      "source_id": "source-id-1",
      "chunk_id": "chunk-id-1",
      "title": "Paper title",
      "snippet": "Short cited excerpt"
    }
  ],
  "summary_steps": [
    "selected 2 documents",
    "retrieved 5 relevant chunks",
    "generated answer with 4 citations"
  ]
}
```

Prompt snapshots, model metadata, hidden internal diagnostics, and detailed execution internals are explicitly deferred to v1. V0 traces should explain what happened without turning the database into a full observability system.

### Agent Run

`AgentRun` records a structured research agent invocation.

Fields:

- `id`
- `agent_name`
- `status`
- `session_id`
- `source_ids`
- `instruction`
- `input_json`
- `steps_json`
- `output_json`
- `citations_json`
- `trace_id`
- `created_by`
- `created_at`
- `updated_at`

### Compute Job

`ComputeJob` is introduced as a forward-compatible model, but v0 may implement it as a disabled or limited stub.

Fields:

- `id`
- `status`
- `language`
- `code`
- `stdout`
- `stderr`
- `result_files_json`
- `created_by`
- `created_at`
- `updated_at`

V0 should not execute arbitrary Python unless a container sandbox with timeout and memory limits is implemented.

## Ingestion Flow

The current worker already performs:

```text
PDF -> text -> chunks -> embeddings -> Qdrant
```

V0 extends this to:

```text
PDF -> text -> chunks -> embeddings -> Qdrant
                |
                v
         structured extraction
                |
                v
         DocumentExtraction
```

Extraction should run after chunking. It can initially use a bounded subset of document text to control latency and context size:

- title and first chunks
- selected high-signal chunks
- optional full-context extraction for short documents

On extraction failure, the source can still be marked ready for ordinary RAG. Extraction status should be visible but must not block basic chat.

## Chat and Research Threads

The existing session chat becomes the Research Thread Engine.

The Research Thread Engine implements the OpenColab research loop:

```text
upload -> question -> cited answer -> saved thread -> reuse -> synthesis -> hypothesis -> next upload
```

Every message should be treated as a reusable research artifact, not an isolated chat turn. V0 achieves this by saving citations, trace summaries, and optional `ResearchObject` records for important discussion outputs and hypotheses.

For each user question:

1. Save the user message.
2. Resolve selected source IDs.
3. Expand groups to leaf sources.
4. Classify retrieval mode as full context or RAG.
5. Retrieve chunks.
6. Build citations from document and chunk metadata.
7. Build a prompt that asks for citation-grounded answers.
8. Stream the LLM response.
9. Save the assistant message.
10. Save a compact `ResearchTrace`.
11. Optionally create or update `ResearchObject` records when the turn produces a reusable discussion or hypothesis.

The WebSocket stream should remain compatible with the current frontend. Citation and trace metadata can be sent as structured events after or alongside token streaming.

Example final WebSocket event:

```json
{
  "type": "done",
  "message_id": "message-id",
  "trace_id": "trace-id",
  "citations": [
    {
      "source_id": "source-id",
      "chunk_id": "chunk-id",
      "title": "Paper title",
      "snippet": "Short cited excerpt"
    }
  ]
}
```

## Citation Design

V0 citations should be simple and reliable:

- A citation points to a source and optionally a chunk.
- A citation includes source title, chunk ID, snippet, and score when available.
- The answer should use inline markers such as `[1]`, `[2]`.
- The right-side panel displays citation cards and opens the related document/source.

V0 does not need perfect page-level PDF citation unless page mapping is already available from parsing. Chunk-level citations are acceptable for v0.

## Agent Runtime

V0 agents are deterministic research pipelines rather than open-ended autonomous agents:

```text
AgentRun
  -> retrieve
  -> synthesize
  -> validate
  -> format_output
```

This keeps the implementation lighter than LangGraph or AutoGen while avoiding pure prompt engineering. Each agent run stores its planned steps in `steps_json`, executes them in a fixed order, and records a compact trace.

Stage responsibilities:

- `retrieve`: load selected sources, extracted structures, and relevant chunks.
- `synthesize`: produce the main analysis or draft.
- `validate`: check that key claims have citations and that required output sections exist.
- `format_output`: return structured JSON plus readable markdown for the UI.

V0 validation is practical rather than exhaustive. It should catch missing citations, empty required sections, and malformed JSON. It does not need a full retry framework, but one bounded repair attempt is allowed when structured output parsing fails.

No external agent framework is required for v0. The important runtime boundary is that agents are staged pipelines with observable outputs, not free-form prompts.

### Literature Synthesizer

Input:

- `source_ids`
- optional user instruction

Output:

- structured comparison
- common methods
- key claims
- agreements and conflicts
- limitations
- research gaps
- suggested next questions
- citations

API:

```http
POST /api/v1/agents/run
```

Request:

```json
{
  "agent": "literature_synthesizer",
  "source_ids": ["source-id-1", "source-id-2"],
  "instruction": "Compare these papers and identify research gaps."
}
```

### Reviewer Assistant

Input:

- paper/source IDs
- review comments as text
- optional target tone or venue

Output:

- issue summary
- response strategy
- evidence needed
- response letter draft
- paper revision checklist
- citations to the paper or supporting sources

Request:

```json
{
  "agent": "reviewer_assistant",
  "source_ids": ["paper-source-id"],
  "instruction": "Prepare responses to these reviewer comments.",
  "input": {
    "review_comments": "Reviewer comments here"
  }
}
```

## API Draft

All routes use the existing `/api/v1` prefix.

Knowledge base:

```http
POST /api/v1/sessions/{session_id}/sources
GET  /api/v1/sources/{source_id}
GET  /api/v1/sources/{source_id}/extraction
GET  /api/v1/sources/search
```

Chat and traces:

```http
WebSocket /api/v1/ws/sessions/{session_id}
GET       /api/v1/sessions/{session_id}/trace
GET       /api/v1/messages/{message_id}/trace
```

Research objects:

```http
GET  /api/v1/research-objects
GET  /api/v1/research-objects/{object_id}
POST /api/v1/research-objects
POST /api/v1/research-objects/{object_id}/relations
```

Agents:

```http
POST /api/v1/agents/run
GET  /api/v1/agents/runs/{run_id}
```

Compute:

```http
POST /api/v1/compute/python
GET  /api/v1/compute/jobs/{job_id}
```

For v0, compute routes may return a clear disabled response unless sandbox execution is implemented:

```json
{
  "status": "disabled",
  "message": "Python execution requires sandbox configuration."
}
```

## Frontend Changes

The frontend should remain React + Vite + Ant Design.

### Chat Workspace

Extend the current session page:

- left: session list or existing navigation
- center: chat transcript
- right: citations and trace panel

The right panel should show:

- citations for the selected assistant message
- source title and snippet
- retrieval score when available
- trace steps
- selected source list

### Knowledge Base

Extend the sources page:

- upload PDF or ZIP
- show processing status
- show extraction status
- show extracted claims, methods, limitations, and datasets
- allow selecting sources for chat or agent runs

### Notebook Timeline

V0 can implement notebook as a lightweight research thread timeline rather than a full notebook editor.

Timeline items:

- uploaded sources
- chat turns
- agent runs
- citations
- conclusions
- future compute jobs

This can initially be a new page or a section within the session view.

## Error Handling

V0 should degrade gracefully:

- If extraction fails, ordinary RAG chat still works.
- If citation creation fails, the answer is still saved but trace records the failure.
- If LLM calls fail, return a clear UI error and save a failed trace event.
- If worker processing fails, mark the source as failed with error details.
- If compute is disabled, return a deterministic disabled response.

Errors must not expose secrets, API keys, or raw environment values.

## Testing Strategy

Backend tests:

- extraction model serialization
- research object relation serialization
- extraction endpoint
- citation creation from retrieved chunks
- trace creation after chat response
- trace payload only includes inputs, retrieval, citations, and summary steps
- agent run request validation
- agent run staged pipeline records retrieve, synthesize, validate, and format_output steps
- disabled compute response

Frontend tests or manual checks:

- upload status still works
- chat stream still works
- citations appear after response
- trace panel opens for a response
- source extraction panel handles pending, ready, and failed states

Fastest relevant checks:

```bash
pytest tests
npm run build
```

If local dependencies are missing, Docker-based verification can be used later in the implementation plan.

## Milestones

### Week 1: Structured Extraction Foundation

- Add extraction model and migration.
- Add extraction service.
- Connect worker pipeline after chunking.
- Add source extraction endpoint.
- Add basic source extraction UI.

### Week 2: Research Thread Trace and Citations

- Add trace and citation models.
- Add ResearchObject model and basic relation support.
- Save trace after WebSocket chat.
- Return citation metadata in WebSocket done event.
- Create discussion or hypothesis objects from reusable thread outputs.
- Add frontend citation and trace panel.

### Week 3: Two Research Agents

- Add agent run model and API.
- Implement Literature Synthesizer.
- Implement Reviewer Assistant.
- Store agent outputs with citations and trace.
- Add minimal agent UI entry points.

### Week 4: V0 Polish and Open Source Readiness

- Add notebook-style timeline.
- Add demo dataset or sample workflow documentation.
- Update README to explain LRAR positioning.
- Add troubleshooting docs.
- Run backend and frontend checks.

## Open Source Readiness Criteria

V0 is ready to announce as an open-source starting point when:

- A new user can start the stack with Docker Compose.
- Admin setup is documented.
- A sample PDF can be uploaded and processed.
- A user can ask a question and receive citations.
- A user can inspect the trace behind an answer.
- Literature Synthesizer works on at least two papers.
- Reviewer Assistant produces a useful response strategy from review comments.
- Secrets are not logged or committed.
- README clearly states what v0 does and does not do.

## Future Direction

After v0, OpenColab can evolve toward:

- PI-led research governance.
- Real workflow checkpoints.
- LangGraph or another durable workflow runtime.
- External literature search and citation graph integration.
- Zotero and BibTeX import/export.
- Secure Docker-based Python execution.
- Notebook-backed experiment records.
- Structured claim-evidence graph.
- Multi-agent literature review and research planning.

These should build on the v0 trace and citation foundation rather than replacing it.
