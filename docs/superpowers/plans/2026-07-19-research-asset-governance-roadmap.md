# Research Asset Governance V1 Delivery Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use superpowers:test-driven-development for every behavior change.

**Goal:** Deliver a lightweight, multi-research-group governed knowledge foundation in which every laboratory material is represented as a versioned ResearchAsset, safe metadata is globally discoverable, protected content is independently authorized, and approved revisions can be used in project RAG.

**Architecture:** `ResearchAsset` is the stable catalog and governance identity; immutable `AssetRevision` and `AssetContentMember` rows describe the actual versioned material. `DataAsset` is an optional scientific-data specialization. A durable knowledge-index event pipeline builds metadata, graph, and content indexes once, while every human or agent content read is checked live through one policy service and one content gateway. Project links provide RAG context but never grant access.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic V2, Alembic, PostgreSQL/SQLite tests, Qdrant, React, TypeScript, Ant Design, React Query, i18next, pytest.

---

## Source of Truth

Implement against:

- `docs/superpowers/specs/2026-07-19-research-data-governance-design.md`
- This roadmap
- The five phase plans listed below

If a phase plan conflicts with the approved design, stop and update the plan before changing production code.

## Delivery Sequence

| Phase | Plan | Depends on | Exit gate |
|---|---|---|---|
| 1 | `2026-07-19-governance-foundation-implementation-plan.md` | None | Existing materials map to governed ResearchAssets with immutable revision/member identity and no implicit PI/Admin content bypass |
| 2 | `2026-07-19-access-workflow-content-gateway-implementation-plan.md` | Phase 1 | Revision-specific requests, approvals, grants, revocation, expiry, audit, and protected-content gateway are enforced |
| 3 | `2026-07-19-multi-format-upload-implementation-plan.md` | Phases 1–2 | Safe direct, archive, external-reference, and scientific formats create one asset revision with an inspectable member manifest |
| 4 | `2026-07-20-governed-lab-knowledge-foundation-implementation-plan.md` | Phases 1–3 | Durable events maintain global metadata, graph, and content indexes; authorization changes take effect without re-indexing |
| 5 | `2026-07-19-research-explorer-project-rag-implementation-plan.md` | Phases 1–4 | Global metadata search works without a project; protected RAG requires a project and live revision authorization |

Do not reorder Phases 1–4. Phase 5 frontend work may begin after the Phase 2 API contracts are stable, but Phase 5 backend integration and final verification must use the completed Phase 4 query service.

## Cross-Phase Invariants

Every phase must preserve these invariants:

1. Every active authenticated laboratory user can discover safe metadata for published L0–L3 assets; L4 is hidden unless an explicit discovery rule matches.
2. `metadata:view` never implies a content capability.
3. PI, administrator, owner, project membership, and `ProjectAssetLink` never create an unconditional content bypass.
4. Ordinary grants and access requests target an immutable revision. Publishing a new revision never extends an existing revision grant.
5. A project session can use an asset revision only when:
   - the asset is linked to that project;
   - the requested revision is eligible under the link;
   - the current user has live `content:use_in_agent`;
   - the asset is active and its catalog, grant, agreement, and policy state permit use.
6. Global search may return safe metadata without a project. L2–L4 content and agent use always require project, purpose, duration, and revision-specific authorization. L0/L1 may use an explicit baseline policy without a project.
7. Content is indexed under a system ingestion identity exactly once per ready revision. Search and RAG authorization are checked before candidate retrieval and again before returning chunks.
8. Grant, revocation, expiry, classification, and project-link changes take effect through live authorization and never require content re-indexing.
9. A ZIP upload creates one ResearchAsset and one AssetRevision containing the original package plus extracted safe members. Any unsafe, nested, encrypted, unknown, or malformed member rejects the whole candidate revision.
10. Raw files and PDFs never leave the local deployment.
11. Logs and user-facing errors never expose storage paths, protected metadata, extracted text, raw content, or hidden L4 existence.
12. All user-facing strings use `en-US` and `zh-CN` i18n keys.
13. All code, identifiers, migrations, comments, logs, errors, and documentation remain English-only.

## Required Capabilities

Use these exact capability values throughout models, schemas, APIs, policy decisions, audit events, and frontend types:

```python
METADATA_VIEW = "metadata:view"
CONTENT_PREVIEW = "content:preview"
CONTENT_DOWNLOAD = "content:download"
CONTENT_USE_IN_AGENT = "content:use_in_agent"
ASSET_MANAGE = "asset:manage"
```

## Classification Values

Use stable lowercase storage values:

```python
PUBLIC = "public"
INTERNAL = "internal"
CONFIDENTIAL = "confidential"
RESTRICTED = "restricted"
TOP_SECRET = "top_secret"
```

The UI maps these to Level 0 through Level 4. Do not persist numeric levels because the string values are clearer in audit records and APIs.

## Migration Compatibility Window

The Phase 1 migration uses this exact mapping:

| Existing `visibility_scope` | New classification | Compatibility behavior |
|---|---|---|
| `lab_public` | `internal` | Active group members receive the former read capabilities |
| `lab_private` | `confidential` | Users who could read through existing rules receive compatibility capabilities |
| `project` | `confidential` | Existing linked-project members receive compatibility capabilities |
| `private` | `restricted` | Owner receives compatibility capabilities |

No existing asset is auto-classified as `public` or `top_secret`.

Compatibility access must be represented as deterministic policy rows plus migration audit events, not as permanent branches in the new policy engine. Remove the legacy authorization fallback only after a production migration report shows zero unmatched accessible users.

Migrated and newly created L0–L3 assets receive the classification baseline for laboratory-wide `metadata:view`; L4 remains hidden by default. Metadata visibility must never be implemented by adding a content capability.

## Shared Verification Commands

Run the fastest relevant checks after each task. Run the full set at each phase boundary:

```bash
backend/.venv/bin/python -m pytest -q
cd frontend && npm run build
pre-commit run
```

Expected result: every command exits with status `0`. A pre-existing deprecation warning from pre-commit configuration is acceptable; new failures are not.

For database work, also run:

```bash
cd backend && PYTHONPATH=. .venv/bin/alembic upgrade head
cd backend && PYTHONPATH=. .venv/bin/alembic downgrade -1
cd backend && PYTHONPATH=. .venv/bin/alembic upgrade head
```

Expected result: upgrade, downgrade, and re-upgrade all exit with status `0` against a disposable development database.

## Phase Completion Checklist

At the end of each phase:

1. Run focused tests named in the phase plan.
2. Run the shared phase-boundary verification commands.
3. Inspect `git diff --check`.
4. Confirm no secret, absolute secure-storage path, protected content, or L4 existence leak appears in changed tests or fixtures.
5. Update the approved design only if an intentional architecture decision changed.
6. Commit using the exact Conventional Commit message in the phase plan.

## Final End-to-End Acceptance

Create these users and assets in a disposable test environment:

- Two research groups: Lab A and Lab B.
- Lab A PI, Lab A PhD student, Lab B postdoc, and an external collaborator.
- One asset at each classification level.
- One parseable DOCX asset, one catalog-only BAM/BAI revision, and one ZIP revision containing multiple safe members.
- One restricted dataset linked to a Lab A project.

Verify:

1. Every active user can find L0–L3 catalog entries permitted by `metadata:view`; unauthorized L4 entries remain absent.
2. `/knowledge/search` returns safe metadata across laboratories without requiring a project; it never returns protected chunks in `lab_global` scope.
3. The Lab A student cannot preview, download, export, or use the restricted dataset before approval.
4. The student can submit a time-bounded request with purpose, project, and exact revision.
5. The correct owner or PI can approve, and the student can then use only that revision in that project session.
6. The Lab B postdoc cannot use the same asset unless both authorization and project linkage exist.
7. Revocation and expiry immediately remove RAG eligibility without requiring a re-index.
8. Publishing revision 2 does not allow a revision 1 grant to read revision 2.
9. The BAM/BAI members remain searchable by safe metadata but never enter text parsing, chunking, embedding, or Qdrant.
10. A malicious ZIP, nested ZIP, spoofed extension, macro-enabled Office file, executable, or unknown archive member rejects the whole candidate revision before it becomes current.
11. Granting or revoking access does not add, remove, or duplicate vector records.
12. Audit events cover discovery, request, approval, grant, preview, download, RAG use, system indexing, denial, revocation, and expiry.

## Out of Scope for V1

Do not add:

- Content-based OCR for images.
- Audio transcription.
- BAM, BAI, SAM, CRAM, CRAI, BCF, BED, GFF, GTF, SEQ, AB1, FASTA, FASTQ, or VCF scientific interpretation.
- Automatic policy mutation based only on AI recommendations.
- Row-level spreadsheet permissions.
- Cross-deployment sharing.
- Permanent hard deletion of audit history.
- A separate physical storage system unless required by the existing file storage abstraction.
