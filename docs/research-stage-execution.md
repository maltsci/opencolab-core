# Innovation and manuscript execution

Stages 3 and 5 use `RESEARCH_STAGE_EXECUTION_v1`. The five-stage research ticket
remains the collaboration and review boundary. The configured Codex runtime
selects available project skills, reads authorized evidence, and writes a typed
result; the application validates it before proposing any accepted project object.
No database migration or additional provider installation is required.

## Stage 3: innovation and feasibility

1. Approve an evidence-bearing Stage 2 baseline. A historical template-only
   baseline cannot substitute for a completed execution record.
2. The proposal executor reads the research question, authorized source texts,
   accepted baseline comparisons and enabled skills. It produces two to five
   distinct routes, each with a hypothesis, approach, success criteria, risks and
   exact evidence quotations. Every route must reference an accepted executed
   baseline. A recommended route is advisory; it is not a claim of global novelty.
3. The researcher selects a route or supplies a revised direction in the ticket.
   The selection records its operator and proposal execution ID.
4. The feasibility executor checks scientific rationale, method validation and
   controls/resources. It must run a small feasibility script, record software
   versions, and save observations and a report. The method-validation finding
   must quote the actual observation artifact, not just a paper or a plan.
5. The proposed protocol includes a hypothesis, steps, endpoints, controls,
   resources, risks and stopping rules. Empty fields are rejected.
6. All checks need evidence-backed `supported` assessments before the protocol
   can be submitted for approval. `unresolved` or `unsupported` findings remain
   visible on a blocked ticket. Human approval is still required before creating
   the accepted protocol and triggering Stage 4.

A successful probe establishes execution, not the ultimate scientific validity
of a method, adequacy of controls, experimental feasibility or expected effect.
Those judgments remain part of protocol review.

## Stage 5: manuscript and claim audit

The writer produces ordered Introduction, Methods, Results, Discussion and
Limitations sections. Each section contains typed plain-text blocks:

- `claim`: a factual assertion with quotations and an evidence basis.
- `interpretation`: an explicitly labeled interpretation with quotations.
- `proposal`: untested work, labeled as proposed rather than observed.
- `limitation`: an explicit evidence or method limitation.

The server assembles the manuscript from those blocks and renders citations
itself. It checks that references exist in the authorized evidence catalog, exact
quotations match, factual numeric tokens appear in their supporting quotations,
and the stated basis matches the actual evidence type. Numeric checks support
decimal, leading-decimal, grouped and scientific notation. They do not establish
unit equivalence, statistical validity, semantic entailment or causal conclusions.

Evidence types remain distinct:

| Type | Admissible origin |
| --- | --- |
| `literature` | Authorized parsed project sources |
| `baseline_result` | Approved baseline object matching its originating ticket's completed execution |
| `protocol` | Approved protocol object matching its supported feasibility execution |
| `empirical_record` | Original observations submitted by an authenticated user on an approved experiment ticket |

Legacy default metrics, automatic PASS rows, generated charts and unsourced
iteration summaries are not empirical observations. Upload provenance is now
recorded when a user submits observations; older records without that provenance
are omitted rather than retroactively labeled authentic. Stage 4's computation
and comparison formulas are unchanged by this work.

Generated output sources, including earlier manuscript PDFs, are excluded from
the primary source corpus to prevent circular citation. Accepted execution objects
are admitted separately under their actual evidence type. Withdrawing an original
baseline source prevents its baseline from grounding new innovation work.

When no authenticated empirical records are available, the draft explicitly states
that experimental validation is not established. Optional model peer review is
shown as a separate advisory result; unavailable review does not become a PASS.
Reference export uses local evidence identifiers and titles as BibTeX `@misc`
entries. Authors, publication dates and DOI values are not invented.

The same writer boundary applies when an academic Deep Research task reaches its
writing checkpoint, including tasks with checkpoints disabled. Intermediate
graph summaries do not automatically become accepted baselines or experiments.

## Artifacts, approval and retry

Every attempt has a fresh directory:

```text
tickets/{ticket_id}/{proposal|feasibility|manuscript}/{execution_id}/
  inputs/manifest.json
  inputs/context.json
  inputs/evidence.json
  inputs/method.md
  outputs/result.json
  execution.json
```

The manifest records source and object revisions, selected skill versions,
hashes and excluded legacy/generated evidence. All input files must remain
unchanged during execution. Output paths must stay under `outputs`, without
symlinks, and obey the existing size limits.

Validated files become governed project assets, accessible through links in the
ticket. Feasibility archives its script, observations, report and structured
result. Manuscript execution archives Markdown, a claim audit, reference export
and its structured result. A PDF is also registered when rendering succeeds.

Approval returns HTTP 409 for missing/failed execution evidence, unresolved
feasibility or an unaudited manuscript. Existing template-only third/fifth-stage
deliverables must be rerun before approval; historical accepted objects are not
rewritten. **Retry** is available in blocked/failed ticket details.

`POST /api/v1/projects/{project_id}/tickets/{ticket_id}/retry-stage` uses existing
project authorization and only accepts open third/fifth-stage tickets. It repeats
the selected feasibility direction when one exists, otherwise regenerates the
proposal; manuscript retry uses current authorized evidence. The existing
`retry-baseline` endpoint remains available for Stage 2.

## Runtime boundaries and validation

Execution uses the configured runtime with `workspace-write` and offline task
instructions. No package installation or external literature lookup is added.
Host/container isolation must enforce the required filesystem and network policy;
task instructions are not a firewall. Select a local model endpoint for isolated
deployment. Attempts still run within the existing request path, not a background
queue; browser requests wait for the backend runtime timeout.

Tests replace the model provider while running local baseline/feasibility scripts.
They cover evidence checks, numeric formats, unresolved feasibility, approvals,
artifact registration, source withdrawal, circular citation, authenticated upload
provenance, retry, project authorization and both manuscript entry points. They
do not establish the scientific quality of a live model's proposals or manuscript.

```bash
backend/.venv/bin/python -c "import asyncio, pytest; result = pytest.main(['tests/test_research_stage_execution.py', 'tests/test_research_superagent.py', 'tests/test_workspace_linkage.py', 'tests/test_baseline_execution.py', 'tests/test_codex_runtime.py', '-q']); import conftest; asyncio.run(conftest.engine.dispose()); raise SystemExit(result)"
cd frontend
npm run build
```

The explicit engine disposal in the test command closes pooled SQLite connections
after pytest finishes, avoiding the local test process's shutdown hang.
