# Development history

## 2026-10-29 — Public core extraction

- Import a clean source snapshot from OpenColab commit `4fa8324` without its Git history, local data, credentials, or untracked files.
- Retain project collaboration, document ingestion and QA, research tasks and skill packs, asset governance, laboratory knowledge and adaptive training.
- Exclude antimicrobial peptide screening and vaccine design code, UI, configuration, tools, dependencies, tests and module documentation.
- Reconnect core database migrations after removing domain tables. This migration graph targets fresh core databases, not an in-place conversion of a full-product database.
- Remove the molecular viewer dependency and domain-specific worker image tooling.
- Default to local PDF processing with no cloud embedding fallback; remote providers require explicit configuration.
- Retain Apache License 2.0 and the target repository's initial history.

See [extraction and maintenance](docs/core-extraction.md) for provenance and future development boundaries.

## Inherited platform milestones

- September–October 2026: bibliographic metadata, previews, knowledge governance consolidation and material access fixes.
- August 2026: research directions, people/resource catalogs, scoped stewards and reviews, maintenance/health views, adaptive training.
- July 2026: LLM profiles, evidence objects and memory, task orchestration, governed library access, skill packs and multi-format ingestion.
- April–June 2026: projects, documents, sharing, extraction, citations and traces.

These are historical development milestones rather than numbered core releases.
