# Evidence-bearing baseline execution

Stage 2 research tickets use `BASELINE_EXECUTION_v1`. The five-stage ticket,
review and project-object flow remains the orchestration layer. A separate
execution service discovers authorized parsed materials and enabled skill packs,
provides a reproduction method, invokes the configured Codex runtime, and
validates evidence before offering a deliverable for review.

## Running a baseline

1. Configure the existing Codex runtime and matching API/sandbox workspace paths.
2. Link readable, processed methods and data to the project. This version exports
   complete parsed text with source/chunk/revision IDs and hashes. It does not
   export raw PDFs, extract data-package ZIPs, or fetch missing datasets.
3. Enable relevant uploaded skill packs in the project policy, or explicitly
   select a pack on the ticket. Only the latest enabled version is offered.
   A built-in reproduction method is available without an uploaded pack.
4. Define a research question or create a baseline-reproduction ticket. The
   executor checks installed dependencies, selects relevant available skills,
   and attempts the documented calculation.
5. Review the deliverable and linked project-material artifacts. Missing
   prerequisites or failures keep the ticket open. After addressing the cause,
   use **Retry** in the ticket detail.

Each attempt has a new execution ID and directory under
`tickets/{ticket_id}/baseline/{execution_id}`. Earlier attempt directories are
retained. The ticket log records attempt IDs and outcomes. A `sources_ready`
trigger can also refresh the open baseline ticket using current authorization.

## Evidence contract

The executor must write `outputs/result.json` according to `BaselineResult` in
`backend/app/services/baseline_execution.py`. A completed result requires:

- A Python, R, or shell script, a separate JSON observations file, and a report.
- A successful Codex command-execution event referencing that script.
- Numeric reported/observed values, units, absolute tolerances and their rationale.
- Exact quotations found in authorized input materials.
- Recorded environment versions and selected skill IDs from the offered catalog.
- Unmodified inputs and nonempty, bounded output files without traversal or symlinks.

The server checks observation/summary agreement and computes whether values are
within the declared tolerance. It archives validated output files as governed
project assets and records SHA-256 hashes. Mismatches are legitimate completed
analyses and remain visible for human review. A validated execution contract is
not independent scientific verification: data choice, methods, units, claims,
tolerances and software suitability still require review. Runtime events establish
execution, not that every submitted number was independently derived correctly.

Blocked or failed attempts propose no baseline objects. Approval returns HTTP
409 unless an open, ready baseline ticket carries completed execution evidence.
This also prevents historical template-only baseline deliverables from being
approved as reproduced; an open historical ticket must be rerun first.

## Runtime and limits

The service requests the existing `workspace-write` sandbox. The task instructions
require offline execution, no installations and no access outside the task
directory. These instructions do not replace host/container network and filesystem
isolation. The configured model endpoint is still used; select a compatible local
provider for air-gapped deployment. No new external database/provider integration
is added.

Inputs are limited to 50 sources, 2 MiB of parsed text per source, and 20 MiB total
including skill files. At most 20 project-selected skills are offered. Each output
file is limited to 2 MiB. Exceeding a limit does not silently truncate scientific
inputs. This first version performs one runtime call per attempt and uses the
existing request execution path, not a background queue. Stages 3 and 5 now use [research stage execution](research-stage-execution.md).
Stage 4 computation and comparison formulas remain unchanged.

## API

`POST /api/v1/projects/{project_id}/tickets/{ticket_id}/retry-baseline`

Uses existing project authorization. Only open baseline tickets can be retried.
The response is the normal ticket response, with
`deliverable.baseline_execution` containing the manifest, comparisons, provenance,
artifact IDs and review requirement. No database migration is needed.

## Verification

```bash
backend/.venv/bin/python -m pytest tests/test_baseline_execution.py tests/test_research_superagent.py tests/test_workspace_linkage.py tests/test_codex_runtime.py -q
cd frontend
npm run build
```

Tests substitute the model provider while executing a real local calculation
script. They do not establish the scientific quality of a live model's choice of
methods or reproduce an external paper end to end.
