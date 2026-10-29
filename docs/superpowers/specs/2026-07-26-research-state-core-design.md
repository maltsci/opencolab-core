# OpenColab Research State Core Design

## Summary

OpenColab's next product milestone will make research continuity the primary value proposition.

A project is a long-lived research environment. It has one active primary research goal, a hierarchy of verifiable sub-goals, a body of accepted research objects, source-grounded evidence, explicit scientific relations, and auditable execution history. Ordinary conversations, productized tasks, skill-pack runs, and workflows all read from and propose changes to this same project state.

Runtime output is not trusted project state by default. Platform Runtime and Codex Sandbox runs may produce answers, citations, artifacts, and proposed state changes. A human confirmation gate promotes reviewed proposals into the project's trusted research state.

The milestone succeeds when a researcher can return to a project after several sessions, understand the current goal, accepted findings, important evidence, unresolved conflicts, and recommended next step without restating the research context.

## Product Decision

The product will follow a **research-state-core-first** strategy.

The implementation will use normal relational current-state models, immutable revisions for important scientific content, and focused audit events for consequential changes. It will not introduce a general graph database or full event sourcing in this milestone.

The sequencing principle is:

```text
Make research state durable
  -> make conversations and tasks update it safely
  -> improve retrieval around the active goal
  -> automate multi-step research plans
```

## Product Goal

Make OpenColab a project-scoped scientific working environment that can answer four questions at any time:

1. What is the project trying to establish?
2. What does the project currently believe?
3. What evidence supports, contradicts, or limits those beliefs?
4. What is the most useful next research action?

## Primary User Outcome

The primary acceptance scenario is cross-session research continuity:

1. A researcher creates or opens a project.
2. The assistant helps draft a structured research goal.
3. The researcher confirms the goal.
4. Ordinary conversations and tasks produce cited answers and proposed state changes.
5. The researcher accepts, edits, or rejects those proposals.
6. The researcher leaves and returns later.
7. OpenColab presents a trustworthy research brief derived from accepted project state.
8. The researcher can continue from a suggested next action without reconstructing context.

## Confirmed Product Principles

### One primary goal per project

A project has one current primary research goal. The primary goal can contain multiple sub-goals that are independently verifiable and completable.

Independent primary research directions should be placed in the backlog or moved into separate projects instead of becoming unrelated parallel roots inside one project.

### AI-guided, human-confirmed goals

The assistant gathers the research question, scope, constraints, and success criteria through conversation. It proposes a structured goal draft. The goal becomes active only after user confirmation.

Subsequent material changes create a new immutable goal revision and require confirmation.

### Proposed changes before trusted state

Conversation and execution paths automatically generate candidate goal revisions, research objects, evidence links, and relations. These changes remain proposed until a user accepts or edits them.

Low-risk proposals may be reviewed in a batch. High-impact goal changes, contradictions, permission changes, and replacements require explicit item-level review.

### Permission inheritance cannot broaden access

Derived scientific state cannot be more visible than the material evidence on which it depends.

If a research object relies on restricted evidence, its effective visibility is at least as restrictive as that evidence. Publishing it to a broader audience requires removing the restricted dependency, producing a reviewed non-sensitive derivation, or completing an explicit release review.

### Evidence is a first-class record

Evidence is not an unstructured field on a relation and not merely another user-facing card type. It is a reusable, source-grounded record connected to research objects and object relations through typed evidence links.

### Frontstage research, backstage runtime

Researchers work with projects, goals, tasks, research state, evidence, and next actions.

Skill packs, workflows, runtime selection, capability manifests, and execution policies remain administrative or runtime concepts unless their status is necessary to explain progress, safety, or failure.

## Scope

### In scope

- Project-level research goal and immutable goal revisions
- Hierarchical sub-goals
- Explicit project ownership and lifecycle for research objects
- First-class evidence and typed evidence links
- Evidence-backed object relations
- Proposed-change review and audit events
- Permission propagation from sources and artifacts to derived state
- One research-context assembly path shared by all runtimes
- A common structured output contract for Platform Runtime and Codex Sandbox
- Goal-aware retrieval and evidence creation from citations
- A project research brief and state-review experience
- Guided multi-step research plans with human checkpoints
- Migration of existing research objects and relation evidence

### Out of scope

- A general-purpose knowledge graph or graph database
- A graph-first default user interface
- A drag-and-drop workflow builder
- A public skill marketplace
- Unattended long-running agents and scheduled research monitoring
- Automatic cross-project knowledge merging
- Full event sourcing
- Direct control of laboratory equipment
- The broader Solution Loop for real experiment execution

## Existing System Baseline

OpenColab already has useful foundations that this design will preserve:

- Project-scoped sessions and project assets
- Permission-aware source access and RAG retrieval
- `ResearchObject` and `ResearchObjectRelation` models
- Research memory shown in session and project surfaces
- Productized task entries backed by platform or Codex runtimes
- Uploaded skill packs executed in an isolated Codex workspace
- Workflow-run and step-run persistence
- Runtime-visible progress and trace summaries

The current gaps are structural rather than purely additive:

- A run goal is currently an input string or message reference, not durable project state.
- Research-object project and session ownership is partly implicit in `content_json`.
- Evidence is split between extracted JSON, citations, and relation metadata.
- Runtime paths do not share a complete research-state input/output contract.
- Project reopening does not yet produce a goal-centered continuation experience.

## Product Architecture

The architecture has five conceptual layers.

```text
Researcher entry points
  - ordinary project conversation
  - productized task
  - guided research plan
            |
            v
Research Context Assembler
  - active goal revision
  - relevant accepted research state
  - authorized sources and evidence
  - bounded conversation context
            |
            v
Permission-aware retrieval and Runtime Router
  - Platform Runtime for lightweight reasoning
  - Codex Sandbox for files, code, and governed skills
            |
            v
Common runtime output
  - answer
  - citations
  - artifacts
  - proposed state changes
            |
            v
Human confirmation gate
            |
            v
Trusted Project Research State
```

### Control plane

OpenColab remains the control plane. It owns:

- project membership and data permissions
- active goal and revision selection
- research-state persistence
- source authorization and retrieval policy
- task and skill availability
- run creation and status
- proposed-change review
- workflow checkpoints
- audit history

### Reasoning and execution planes

Platform Runtime handles lightweight conversation, goal clarification, explanation, and synthesis that does not require filesystem or code execution.

Codex Sandbox handles governed skill execution, file processing, code execution, statistics, and other computation that requires an isolated workspace.

Neither runtime owns project truth. Both consume a frozen context manifest and return the same logical output contract.

## Core Domain Model

### Project

The project remains the durable scientific environment and top-level access boundary.

It gains a reference to its current primary research goal. A project can retain completed, abandoned, or superseded goals for history, but only one primary goal is active at a time.

### ResearchGoal

`ResearchGoal` is the stable identity and lifecycle record for a primary goal or sub-goal.

Conceptual fields:

- `id`
- `project_id`
- `parent_goal_id`
- `current_revision_id`
- `status`: `draft`, `active`, `paused`, `achieved`, `abandoned`
- `created_by`
- `created_at`
- `updated_at`

Project-level integrity rules enforce one active root goal per project. Sub-goals can be active in parallel beneath that root.

### ResearchGoalRevision

`ResearchGoalRevision` stores immutable confirmed content for a goal.

Conceptual fields:

- `id`
- `goal_id`
- `revision_number`
- `research_question`
- `rationale`
- `scope_json`
- `constraints_json`
- `success_criteria_json`
- `change_summary`
- `created_by`
- `created_by_type`
- `created_at`

A material goal edit creates a new revision. Runs and proposals retain the exact revision ID used to produce their output.

### ResearchObject

`ResearchObject` expresses the project's current scientific understanding. It is not a chat message and not a run artifact.

Initial canonical types:

- `claim`
- `hypothesis`
- `finding`
- `gap`
- `decision`
- `note`

Conceptual fields:

- `id`
- `project_id`
- `type`
- `current_revision_id`
- `status`: `active`, `challenged`, `superseded`, `archived`
- `effective_visibility`
- `created_by`
- `created_at`
- `updated_at`

Research objects may be linked to one or more goals or sub-goals through an association table. The association can mark one goal as the primary organizing context.

### ResearchObjectRevision

Accepted research-object content is not silently overwritten. Material edits create immutable revisions containing:

- title
- narrative content
- structured content
- change summary
- author or generating run
- timestamp

A conclusion that replaces another conclusion should use a `supersedes` relation in addition to revision history when both scientific statements remain meaningful.

### Evidence

`Evidence` is a reusable source-grounded observation or result.

Conceptual fields:

- `id`
- `project_id`
- `source_kind`: source chunk, run artifact, or human observation
- `source_id`
- `locator_json`
- `excerpt`
- `summary`
- `structured_payload_json`
- `extraction_confidence`
- `verification_status`: `unverified`, `verified`, `rejected`, `unavailable`
- `permission_snapshot_json`
- `effective_visibility`
- `generated_by_run_id`
- `verified_by`
- `created_at`
- `updated_at`

The locator must be precise enough to reopen the supporting material, such as a document chunk, page and paragraph, table cell, artifact path, or run output field.

The permission snapshot records why the evidence was usable at creation time. Every later read still performs a live authorization check.

### Evidence links

Typed links connect reusable evidence to scientific statements.

Separate object-evidence and relation-evidence associations preserve database integrity without polymorphic foreign keys.

Link fields include:

- evidence ID
- target object or relation ID
- direction: `supports`, `contradicts`, `contextualizes`, or `limits`
- strength or relevance
- rationale
- creator and creation source
- review status

Human verification state and model confidence remain separate concepts.

### ResearchObjectRelation

The existing relation model remains the scientific logic layer and is extended rather than replaced.

Initial relation types should remain intentionally bounded:

- `supports`
- `contradicts`
- `depends_on`
- `derived_from`
- `supersedes`
- `addresses`

Relations gain project ownership, lifecycle state, revision provenance, and optional linked evidence.

### ProposedChange

`ProposedChange` is the only runtime-to-state write boundary.

Conceptual fields:

- `id`
- `project_id`
- `change_type`
- `payload_json`
- `based_on_goal_revision_id`
- `source_message_id`
- `source_run_id`
- `source_skill_pack_id`
- `source_skill_pack_version`
- `permission_dependencies_json`
- `effective_visibility`
- `status`: `proposed`, `accepted`, `edited`, `rejected`, `stale`
- `risk_level`
- `reviewed_by`
- `reviewed_at`
- `created_at`

Accepted proposals are applied transactionally and record the IDs and revisions they create or modify.

A proposal based on an outdated goal revision becomes stale and requires explicit re-evaluation or review.

A proposal inherits the most restrictive visibility of the context entries used to produce it. Proposal lists, counts, and review actions apply the same live authorization checks as formal research state.

### ResearchAuditEvent

Focused audit events record consequential state transitions without introducing full event sourcing.

Events include:

- goal activation and revision
- proposal acceptance, edit, rejection, and staleness
- object challenge, replacement, and archival
- evidence verification or loss of access
- effective-permission changes
- workflow checkpoint decisions

## Research-Object Lifecycle

Runtime-generated candidates follow this path:

```text
generated -> proposed -> accepted -> challenged -> superseded or archived
                    \-> rejected proposal audit record
```

Rules:

- Generated output is not persisted as a research object before proposal creation.
- Rejected proposals do not create formal research objects.
- Accepted objects are immutable through revision records.
- Challenged objects remain visible with their challenge and contradictory evidence.
- Superseded objects remain available for historical explanation but are excluded from default current-state summaries.

## Goal-Aware Research Context

The `ResearchContextAssembler` becomes the single context policy boundary for ordinary conversation, tasks, skill packs, and workflows.

### Mandatory context

Every research run receives:

- project identity
- active goal identity and exact revision
- active sub-goal when selected
- goal scope, constraints, and success criteria
- user identity and runtime authorization scope

### Retrieved context

The assembler retrieves only what is relevant to the current intent:

- accepted research objects
- active relations
- verified and unverified evidence with explicit labels
- unresolved conflicts and gaps
- authorized source chunks
- authorized run artifacts

### Bounded conversation context

Recent messages provide local conversational continuity. Full conversation history is not treated as durable project memory and is not automatically loaded.

Important prior content should enter future context through accepted research state or focused retrieval.

### ContextManifest

Every run freezes an auditable context manifest containing:

- project and goal revision IDs
- selected sub-goal IDs
- source, evidence, object, and artifact IDs
- permission decisions and policy version
- runtime and sandbox profile
- task, workflow, and skill-pack versions

The manifest contains references and safe metadata. Raw project files remain local and are mounted into a sandbox only when explicitly authorized.

## RAG as the Knowledge Entry Layer

RAG is responsible for authorized evidence discovery, not for owning project state.

### Retrieval pipeline

1. Classify the research intent.
2. Resolve the active goal and relevant sub-goal.
3. Build the authorized candidate source set.
4. Decompose or rewrite the query when needed.
5. Perform hybrid vector and metadata retrieval.
6. Rerank by query relevance, goal relevance, source quality, and useful source diversity.
7. Preserve exact source and artifact locators.
8. Return context to the selected runtime.
9. Convert cited passages or results into evidence proposals when appropriate.

### Retrieval behavior

- Goal content influences ranking but does not replace the user's immediate query.
- Accepted objects can be retrieved as project state, but they must not be presented as external evidence.
- Contradictory evidence should be retained rather than filtered out for consistency.
- Empty or weak retrieval produces an explicit insufficient-evidence result.
- Retrieval never expands the authorized source set.

### Evaluation dataset

Phase 2 includes a project-like offline evaluation set covering:

- specific fact questions
- project overview questions
- source comparison
- evidence contradiction
- research-gap identification
- permission-restricted sources
- no-answer cases

Evaluation measures retrieval relevance, citation accuracy, source coverage, contradiction recall, and correct refusal.

## Runtime Routing and Contracts

### Runtime selection

Platform Runtime is preferred for:

- goal clarification
- ordinary project conversation
- explanation
- lightweight synthesis over authorized text context

Codex Sandbox is selected for:

- file parsing or transformation
- code execution
- statistical analysis
- governed skill-pack execution
- tasks requiring a prepared workspace or generated artifacts

The researcher does not need to select a runtime manually in the normal path.

### Common output contract

Both runtimes return the same logical envelope:

```json
{
  "answer": {},
  "citations": [],
  "proposed_changes": [],
  "artifacts": [],
  "diagnostics": {}
}
```

The concrete schema must be versioned. Runtime adapters normalize provider-specific or sandbox-specific responses before persistence.

Only citations that resolve to authorized context-manifest entries can become evidence proposals.

Invalid proposed-change payloads do not block a valid user-facing answer, but they are discarded or retried as a unit and recorded in diagnostics.

## Agent Skill Product Model

### Skill Pack

A skill pack is an administrator-installed and governed capability bundle.

In addition to `SKILL.md`, scripts, dependencies, and reference assets, each pack must declare a machine-readable capability manifest containing:

- task types and input schema
- output and artifact types
- allowed proposed-change types
- filesystem requirements
- CPU, memory, GPU, and timeout requirements
- network and tool permissions
- accepted data classifications
- compatibility and version information
- failure and retry policy

### Task

A task remains the researcher-facing product entry. It explains the research job, required inputs, expected outputs, and project context it uses.

Tasks should be recommended in relation to the active goal or sub-goal instead of presented only as an independent capability catalog.

### Workflow

A workflow is a backstage executable composition. It answers how a multi-step task executes.

Every workflow run freezes:

- goal revision
- context manifest
- workflow version
- skill-pack versions
- step inputs and outputs
- artifacts and citations
- checkpoint decisions
- state-write results

### Guided Research Plan

The researcher-facing representation of Level 2 automation is a guided research plan, not a workflow editor.

A plan:

- advances one selected sub-goal
- presents meaningful research steps
- exposes progress and failures
- pauses at consequential checkpoints
- resumes idempotently
- ends with a proposed project-state update

OpenColab may implement the plan with a fixed workflow, Codex-guided orchestration, or a governed combination. That implementation choice does not change the researcher-facing model.

## Data Permission Model

### Effective visibility

Evidence effective visibility is derived from its source or artifact authorization.

Research-object and relation effective visibility is the most restrictive effective scope among all active linked evidence and any explicit object-level restriction. Removing, rejecting, making unavailable, or adding an evidence link triggers recomputation. A broader publication requires a separately reviewed public derivation with no restricted evidence dependency.

Derived visibility is cached for efficient listing but recomputed when dependencies or source permissions change.

### Three authorization points

1. **Before retrieval:** build an authorized source and evidence candidate set.
2. **Before materialization:** recheck live access before opening evidence, files, or artifacts.
3. **Before publication:** verify that the derived state can be shared at the requested scope.

### Revoked access

When source access is revoked:

- the evidence locator remains for audit
- content is not shown to unauthorized users
- verification status can become `unavailable`
- dependent object grounding is recomputed
- project briefs mark unsupported or restricted conclusions instead of silently presenting them

### Local-first boundary

Raw data and PDFs remain local. In explicit hybrid mode, only approved preprocessed text chunks may be sent to a cloud model.

Codex workspaces receive only files and references listed in the context manifest. Skill-pack capability policy cannot grant access beyond the invoking user's project permissions.

## Researcher Experience

### Project Research Cockpit

The project home becomes the default continuation surface.

The first viewport contains:

- current primary goal and revision
- scope and important constraints
- sub-goal progress
- current consensus
- important unresolved contradiction or evidence gap
- recommended next research action
- direct entry into ordinary conversation
- relevant task suggestions
- count of pending state proposals

### Research brief

The brief is generated from accepted state, not from an unconstrained summary of chat history. It is assembled for the current viewer and must not expose restricted object titles, excerpts, counts, conflict indicators, or inferred facts through aggregation.

It includes:

- current goal
- accepted findings and hypotheses
- strongest supporting and contradicting evidence
- unresolved gaps
- decisions and rationale
- recent meaningful changes
- recommended next actions

Every substantive brief item links back to research objects and evidence.

### Research State panel

The project workspace exposes a compact state panel with:

- accepted state
- pending proposals
- sources and evidence
- filters by goal, type, status, and conflict

A graph view can be added later as an advanced exploration surface. It is not the default representation.

### Proposal review

After an answer or task run, the UI presents a consolidated change summary.

Users can:

- inspect the source, permissions, and run provenance
- accept an item
- edit and accept an item
- reject an item with an optional reason
- accept a batch of low-risk independent items
- defer review

Goal revisions, superseding claims, high-impact contradictions, and broader publication requests cannot use blind batch acceptance.

## Error Handling and Recovery

### Retrieval returns no useful evidence

The assistant answers from clearly labeled project state when appropriate or reports insufficient evidence. It does not generate source-grounded proposals without resolvable citations.

### Runtime execution fails

The run, completed step records, and valid artifacts remain available. No trusted state change is applied. The user receives a concise failure summary and a retry or recovery option.

### Structured output is invalid

A valid answer may still be shown. The invalid proposal batch is rejected or retried by the adapter and logged without partially writing formal state.

### Goal revision changed during a run

The run completes against its frozen revision. Its proposals are marked stale if the active goal revision has changed and require explicit review or regeneration.

### Workflow partially completes

The workflow resumes from a durable, idempotent checkpoint. Replayed steps cannot create duplicate objects, evidence links, relations, or artifacts.

### Evidence becomes unavailable

The affected object remains visible only where policy permits, is marked as having unavailable grounding, and is excluded from strong-consensus summaries until reviewed or supported by other evidence.

## Testing and Evaluation

### Domain-model tests

- one active root goal per project
- goal and object revision immutability
- valid lifecycle transitions
- relation uniqueness and project consistency
- evidence-link target integrity
- transactional proposal application
- stale proposal detection

### Permission tests

- authorized candidate-set construction
- retrieval cannot return inaccessible sources
- evidence read rechecks live access
- artifact mounting follows the context manifest
- derived visibility uses the most restrictive dependency
- source revocation updates dependent state
- hybrid mode never sends raw files or unauthorized chunks

### Runtime-contract tests

- Platform Runtime and Codex adapters produce the same envelope version
- citations resolve only to manifest entries
- invalid proposals cannot partially write state
- answer persistence is independent from proposal acceptance
- skill-pack and workflow versions are frozen in run provenance

### End-to-end product tests

- create project and confirm goal
- continue ordinary conversation
- run a productized task
- review and accept proposed changes
- leave and reopen project
- verify the research brief reflects accepted state
- challenge an accepted object with contradictory evidence
- revoke source permission and verify safe degradation
- fail and resume a guided research plan without duplicate writeback

### Skill-pack security tests

- ZIP path traversal and symlink rejection
- manifest validation
- filesystem isolation
- network denial and allow-list behavior
- CPU, memory, GPU, and timeout enforcement
- secret and environment isolation
- unauthorized project-file access
- duplicate or forged artifact registration

## Success Measures

### Continuity

In usability testing, a returning researcher can identify the active goal, current state, main unresolved issue, and next recommended action without rereading conversation history.

### Grounding

Accepted substantive claims, findings, and hypotheses expose accessible evidence or an explicit evidence-gap state. Notes and human decisions may remain intentionally non-evidentiary but are labeled as such.

### Proposal quality

The product measures acceptance, edit, rejection, deferral, duplication, and staleness rates by proposal type. Rejection reasons feed retrieval and extraction evaluation, not automatic model training without separate consent.

### Safety

Permission red-team tests produce no unauthorized retrieval, context inclusion, artifact mount, evidence display, or derived publication.

### Reproducibility

Every task or workflow output can identify the goal revision, context manifest, runtime profile, task definition, workflow version, and skill-pack versions that produced it.

## Delivery Roadmap

### Phase 0: Research State Foundation

Target duration: approximately two weeks.

Deliverables:

- goal and goal-revision models
- sub-goal hierarchy
- project ownership and revision support for research objects
- first-class evidence and evidence links
- proposed changes and audit events
- permission propagation rules
- migration and model-invariant tests

Exit gate:

- domain invariants and permission tests pass
- legacy state is readable after migration
- no runtime can bypass the proposed-change boundary

### Phase 1: Cross-session Research Loop

Target duration: approximately three to four weeks.

Deliverables:

- AI-guided goal draft and confirmation
- project research cockpit
- research brief generated from accepted state
- common runtime output envelope
- proposal review and batch acceptance for low-risk items
- ordinary conversation using the research-context assembler
- end-to-end cross-session continuation tests

Exit gate:

- a researcher can return and continue without restating project context
- the brief cites accepted state and evidence
- proposal review visibly changes the next project brief

Phase 0 and Phase 1 form one product milestone. Shipping the persistence layer without the continuation experience does not validate the product direction.

This document is a program-level product design. The first implementation plan covers only the combined Phase 0 and Phase 1 milestone. Phase 2 and Phase 3 each require a separate reviewed specification and implementation plan after the preceding exit gate is met.

### Phase 2: Goal-Aware RAG and Evidence

Target duration: approximately two to three weeks.

Deliverables:

- shared research-context assembler for all execution paths
- hybrid retrieval and goal-aware reranking
- citation-to-evidence proposals
- contradiction, gap, and insufficient-evidence handling
- retrieval evaluation dataset and reports

Exit gate:

- citation and permission evaluation pass
- contradiction and no-answer cases degrade explicitly and safely

### Phase 3: Guided Automation

Target duration: approximately three to four weeks.

Deliverables:

- skill-pack capability manifest
- frozen run context and version provenance
- sub-goal-centered guided research plans
- human checkpoints
- retries, idempotent resume, and state-write recovery
- multi-step end-to-end safety tests

Exit gate:

- failed plans resume without duplicate state or artifacts
- consequential state writes always pass through confirmation

## Migration Strategy

### Research objects

Backfill `project_id` from the session reference currently stored in object content where possible, then resolve the session's project.

Objects that cannot be assigned safely remain legacy private records owned by their creator until explicitly attached to a project. Migration must not guess a broader project scope.

Existing `hypothesis` objects retain their type. Existing `discussion` objects remain readable and are progressively normalized to `note`, `finding`, or `decision` when reviewed; migration does not infer scientific meaning automatically.

### Relations and evidence

Existing relation rows remain valid.

Relation metadata containing a resolvable source or chunk reference can be migrated into Evidence and RelationEvidenceLink records. Free-text evidence without a resolvable source remains legacy rationale and is not upgraded to verified evidence.

### Runs and workflows

Existing runs remain readable without a context manifest. New runs use the versioned manifest and output envelope. Historical runs are not assigned fabricated goal revisions or skill versions.

## Product Risks and Mitigations

### Review fatigue

Too many small proposals can make the confirmation model unusable.

Mitigations:

- deduplicate semantically equivalent proposals
- group related changes by run and sub-goal
- rank by scientific impact and risk
- allow low-risk batch acceptance
- learn per-project review preferences without silently accepting high-impact changes

### False certainty

Models may present inference as observation.

Mitigations:

- separate object type, evidence direction, model confidence, and human verification
- require source locators for evidence proposals
- preserve contradictory evidence
- label insufficient grounding

### Scope expansion

The six product areas can become independent programs and delay user value.

Mitigation:

Cross-session research continuity is the sole phase-level product acceptance thread. Work that does not help establish, ground, continue, or safely automate that loop is deferred.

## Final Product Position

OpenColab should not be positioned primarily as a chat application, a knowledge graph, a workflow tool, or a skill marketplace.

It is a local-first research environment where:

- goals define what the project is trying to establish
- research objects express current scientific understanding
- evidence explains why that understanding is credible or contested
- permissions protect original and derived knowledge
- skills provide governed research capabilities
- workflows automate visible, recoverable research plans
- every conversation and run can contribute to a durable, human-confirmed research state
