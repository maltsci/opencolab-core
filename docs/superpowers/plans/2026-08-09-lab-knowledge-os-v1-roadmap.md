# Lab Knowledge OS v1 Implementation Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement each phase plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved Lab Knowledge OS v1 as five independently testable phases without weakening existing project or asset permissions.

**Architecture:** PostgreSQL remains the authority for people, directions, explicit domain relations, governance, and history. Qdrant remains a content-retrieval index whose hits are re-authorized against PostgreSQL before display or LLM use; the React client gains product surfaces only after the corresponding backend contracts pass phase exit criteria.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Alembic, Pydantic v2, PostgreSQL, Qdrant, pytest, React, TypeScript, Ant Design, React Query, i18next.

---

## Planning Strategy

The approved PRD contains five subsystems with different risk profiles. Do not execute it from one monolithic plan. Create and approve one detailed plan per phase after the prior phase fixes the interfaces consumed by the next phase.

| Phase | Deliverable | Detailed plan | Entry gate | Exit gate |
|---|---|---|---|---|
| 0 | Shared foundation and requirements baseline | `docs/superpowers/plans/2026-08-09-lab-knowledge-os-v1-foundation.md` | Approved PRD and green baseline | Domain/security review, reversible migration, frozen 30-question benchmark |
| 1 | Resources catalog extension | `docs/superpowers/plans/2026-08-09-lab-knowledge-os-v1-resources.md` | Phase 0 APIs and direction identifiers stable | Searchable key resources, no permission regressions, actionable resource states |
| 2 | People and Research surfaces | `docs/superpowers/plans/2026-08-09-lab-knowledge-os-v1-people-research.md` | Phase 1 resource metadata stable | Profile/direction completeness, minimal activity projection, actionable empty states |
| 3 | Unified Assistant | `docs/superpowers/plans/2026-08-09-lab-knowledge-os-v1-assistant.md` | Entity query contracts stable and benchmark frozen | 90% answerability, 80% factual correctness, zero permission leakage |
| 4 | Continuous maintenance and operations | `docs/superpowers/plans/2026-08-09-lab-knowledge-os-v1-operations.md` | Core entities and Assistant in pilot use | Steward queues, freshness reminders, local adoption metrics, v1.5/v2 decision record |

Create each later phase file only after reviewing evidence from the previous phase; the fixed names above keep cross-references stable.

## Approved PRD Coverage

| Approved requirement | Delivery location |
|---|---|
| Knowledge OS as the Discovery Loop foundation; ResearchObject graduation path | Phase 0 Tasks 1, 3, and 5; final v1 review gate |
| Explicit people, project, resource, ResearchObject, and direction relations | Phase 0 Tasks 1–3; Phases 1–2 product surfaces |
| Scoped Knowledge Steward with human approval and audit history | Phase 0 Tasks 4–5; Phase 4 operations |
| Current-permission enforcement and immediate revocation | Phase 0 Task 6; every later phase exit gate |
| Real 30-question baseline and Assistant quality thresholds | Phase 0 Task 7; Phase 3 evaluation |
| Reversible migration and conflict handling | Phase 0 Tasks 1 and 8 |
| Resources before People/Research, minimal activity projection, unified Assistant | Phases 1–3 in roadmap order |
| Empty states, freshness, opt-out, notifications, adoption metrics, and i18n | Phases 1, 2, and 4, with cross-phase i18n invariant |

No approved requirement is left without a delivery phase. Detailed Phase 1–4 task plans are intentionally gated on the contracts and evidence produced by the preceding phase.

## Cross-Phase Invariants

- Never send raw files or unauthorized content to an external model.
- Re-authorize every Qdrant hit against current PostgreSQL policy before returning it or sending it to an LLM.
- Keep `ResearchDirection` separate from process-oriented `ResearchObject` records.
- Use explicit foreign-key association tables for authoritative domain relations; do not introduce a universal entity table.
- AI writes only `KnowledgeSuggestion` records. A human with field-level authority must approve before authoritative state changes.
- Do not auto-accept stale suggestions.
- Archive or expire entities and relations; do not erase history required for audit.
- All user-visible strings use en-US and zh-CN i18n keys.
- Structured API budgets at target scale are p95 under 200 ms for reads and under 500 ms for writes.
- Every behavior change follows red-green-refactor and lands as a small Conventional Commit.

## Phase 0 Manual Product Gate

Before Phase 0 is declared complete, the product owner, PI, and real lab members must supply 30 verbatim benchmark questions. Engineering provides the schema and validator; engineering must not invent or rewrite the questions to improve model scores.

The real question and rubric text stays in the gitignored local file `evaluation-data/lab-knowledge-os-v1-benchmark.zh-CN.json`. Git stores only its schema, offline validator, tests, and a checksum/count manifest with no question text, answer text, source titles, or personal identifiers.

Required distribution:

- 8 people-finding questions.
- 8 research-direction questions.
- 8 resource-finding questions.
- 6 cross-entity exploration questions.
- At least 6 questions whose correct result is an explicit no-answer or permission-limited response.
- At least 6 questions evaluated under two users with different permissions.

## Planning Gates for Later Phases

### Phase 1 plan inputs

- Approved Phase 0 OpenAPI contracts and migration schema.
- Real key-resource inventory sample.
- Confirmed resource metadata field matrix for data, code, model weights, and GPU directory entries.

### Phase 2 plan inputs

- Approved Resources API and UI behavior.
- Real member/profile sample and official direction inventory.
- Confirmed minimal activity types that may appear in derived profile and direction feeds.

### Phase 3 plan inputs

- Frozen 30-question benchmark and evaluator rubric.
- Stable entity-detail URLs and Assistant session-scope contract.
- Completed revocation threat model and automated authorization regression suite.

### Phase 4 plan inputs

- Pilot usage evidence from Phases 1–3.
- Steward workload and stale-record counts.
- Approved privacy-preserving local event definitions for adoption metrics.

## Final v1 Review Gate

When all five phases pass, hold a product and architecture review. The review must decide whether v1.5/v2 prioritizes these Discovery Loop integrations:

1. Use Research Direction background, members, and resources as hypothesis-generation context.
2. Organize contradiction and gap objects under Research Directions.
3. Filter literature retrieval by Research Direction.

Record the decision in a new approved spec before implementing any of these integrations.
