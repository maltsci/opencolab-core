# Core extraction and future maintenance

## Provenance and scope

OpenColab Core was extracted on 2026-10-29 from the committed source snapshot of `maltsci/opencolab` at `4fa8324`. The public target is `https://github.com/maltsci/opencolab-core`. The target's initial commit/history is retained; source repository Git history, untracked files, local environment files, uploaded research data, model weights and runtime caches are not imported.

Retained capabilities: project collaboration, document ingestion and previews, evidence-grounded QA, research objects/memory, tasks and Codex skill packs, access governance, laboratory knowledge directories/reviews/maintenance, adaptive training, model administration and deployment scripts.

Excluded capabilities: antimicrobial peptide screening and vaccine design, including their API/UI, worker loops, models/schemas, dedicated migrations, tools, fixtures, tests, scientific documentation and exclusive dependencies. General research vocabulary in retrieval or synthetic tests does not represent an installed domain workflow.

The source Apache-2.0 license and necessary attribution are preserved. Third-party dependencies and separately obtained model weights retain their own terms.

## Database boundary

Core uses a fresh database. Domain table migrations were removed; the training branch boundary and member archival chain were reconnected, and notifications now extend the preceding core revision. Existing full-product databases can contain removed Alembic revision identifiers and must not be pointed at this code as an upgrade shortcut. This extraction does not migrate production data or change the source installation.

## Configuration differences

Core starts no domain workers and fetches no domain models. The worker image does not install sequence tools or a browser for external prediction. PDF parsing defaults to local processing; remote OCR has no preset host. Cloud embedding fallback defaults to `none`. Optional cloud services still exist and require deliberate operator configuration. See [deployment](deployment.md).

## Validation

Before publishing, run the retained backend tests, frontend production build, migration graph checks and a fresh-database migration. Scope regression tests ensure removed domain routes/tables are absent and core migration parents resolve. A static extraction is not an end-to-end deployment acceptance test; locally reused dependency environments must be distinguished from a clean image build.

## Future development

Make general platform changes in this repository first. Keep domain work in the separate full-product repository. Prefer small commits confined to core or domain behavior so fixes can be transferred deliberately. Do not mirror or push the private repository's full branches into this public repository.

Because the extraction intentionally does not share the original source Git ancestry, adding this repository as an `upstream` remote is not enough for conflict-free merges. Initially, backport selected core commits with reviewed `cherry-pick` operations or patches in the private repository. Do not use `--allow-unrelated-histories` as a routine synchronization strategy.

A later, separately reviewed rebase of the full product onto this public core can establish shared ancestry and reapply domain functionality as dedicated commits. That is not part of this extraction, and it must not rewrite or remove the existing product's data or published history accidentally. Once both repositories have a verified common baseline, normal upstream merges become practical.

## Known inherited limitations

The frontend production bundle exceeds Vite's default chunk warning threshold.
The frontend lint script has no committed ESLint configuration and cannot start.
These are separate follow-up tasks; extraction does not claim they are resolved.
Validation reuses the existing local Python/Node dependency installations rather
than rebuilding every image from scratch. Deployment operators must still supply
local model caches and validate their configured model/runtime connections.

## Extraction verification results (2026-10-29)

- Retained backend regression suite: **664 passed** (357.14 seconds), including new scope/migration-boundary tests.
- TypeScript and Vite production build: passed; Vite reported the inherited large-chunk warning.
- Fresh PostgreSQL 14 migration: all revisions through `t4u5v6w7x8y9` applied; 74 tables, with no excluded domain tables.
- Post-migration API smoke check: initial admin seeding, login and project creation passed; excluded domain routes returned 404.
- Both Compose modes parsed successfully with validation-only configuration values.
- Backend static imports, shell syntax, 97 current-document links/anchors and staged whitespace checks passed.
- Pre-commit ran successfully; its current configuration has only a push-stage test hook, so backend regression was run separately.
- Frontend lint could not start because the inherited source has no ESLint configuration.

Optional dependencies retained shutdown threads after pytest completed. The test
runner recorded pytest's session exit status (0), then terminated only the
completed test process. This does not conceal an interrupted test run. The suite
also reports inherited deprecation/collection warnings. No full Docker image
rebuild or live model-inference acceptance test was performed during extraction.
