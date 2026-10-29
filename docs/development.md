# Development and contributing

Use Python 3.12 for the backend environment and a Node.js version compatible with the committed Vite toolchain; the frontend container uses Node 20. Run all Python installation/testing commands through `backend/.venv`. Do not install project dependencies globally. The [deployment guide](deployment.md) describes the Compose alternative.

## Local environment

From the repository root:

```bash
cp .env.template .env
python3.12 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
npm --prefix frontend ci
```

Edit `.env` locally using the required values in the deployment guide. The template uses host PostgreSQL port 8432 and Qdrant port 8433; containers use their internal ports instead. Keep API and worker configuration consistent. Do not commit credentials, local research files or downloaded models.

For the standard host development flow:

```bash
./scripts/start-dev.sh
./scripts/status-dev.sh
./scripts/stop-dev.sh
```

The start script starts dependency containers, applies `alembic upgrade heads`, and runs the API, worker and Vite as host processes. It can stop existing listeners on ports 8000, 8001 and 5173; inspect a shared machine before running it. It does not start the Codex sandbox. To test Codex tasks, provision that service separately with the required shared authentication, compatible model endpoint and workspace paths; the Compose stack is the simpler complete topology.

| Host process | Address |
|---|---|
| Frontend | `http://localhost:5173` |
| API and Swagger UI | `http://localhost:8000`, `/docs` |
| Worker | `http://localhost:8001` |

Run one application mode at a time: host and Compose workers share the same database/run queue by default.

To run the API manually after dependencies are available:

```bash
source backend/.venv/bin/activate
cd backend
PYTHONPATH=. alembic upgrade heads
PYTHONPATH=. uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API alone does not provide background document processing. Use the normal development script for the worker or inspect `backend/app/worker/main.py` for its startup configuration.

## Configuration

General runtime settings resolve in this order: database configuration, environment variables, `.env.{OPENCOLAB_ENV}`, then `.env`. The default environment is `dev`. Bootstrap database, JWT secret and Qdrant connection settings cannot be changed through the runtime settings UI. LLM profiles additionally determine the active model connection; check both profile selection and runtime settings when diagnosing a model change.

Canonical key definitions are in [`backend/app/core/config.py`](../backend/app/core/config.py), runtime resolution in [`backend/app/services/runtime_config.py`](../backend/app/services/runtime_config.py), and examples in [`.env.template`](../.env.template). Services can also read their own settings/environment; changing `.env` is not proof that an already running worker reloaded a value.

An explicitly configured `OPENCOLAB_LLM_API_KEY` overrides provider-specific environment keys. When empty, LiteLLM can resolve provider credentials from the environment. Never paste keys into issues, screenshots or logs.

## Checks

Run the fastest check relevant to a change first. Examples from the repository root:

```bash
backend/.venv/bin/python -m pytest tests/test_auth.py -q
backend/.venv/bin/python -m pytest tests/test_research_asset_governance.py -q
backend/.venv/bin/python -m pytest tests/test_training_courses.py -q
npm --prefix frontend run build
```

The inherited frontend package defines `npm run lint`, but no ESLint configuration was committed in the source snapshot; that command currently cannot start. The production TypeScript/Vite build is the available frontend check. Add a reviewed lint configuration separately.

Full backend regression run:

```bash
backend/.venv/bin/python -m pytest
```

The ordinary API/service test harness uses in-memory SQLite without PostgreSQL/Qdrant. Optional integration checks can require local artifacts, optional packages, executables, or explicit opt-in; inspect skips and the selected test file rather than treating a skipped model check as inference validation. Standalone scripts that contact external predictors are not ordinary offline unit tests.

Install hooks inside the project environment:

```bash
source backend/.venv/bin/activate
python -m pip install pre-commit
pre-commit install
pre-commit install --hook-type pre-push
pre-commit run --all-files
```

Always run pre-commit before committing. The current hook configuration defines the pytest hook for the push stage; the default pre-commit-stage run is not a replacement for tests/build checks. To invoke that hook explicitly:

```bash
pre-commit run --hook-stage pre-push --all-files
```

## Source and API navigation

- API router registration: [`backend/app/main.py`](../backend/app/main.py).
- Frontend routes and access-aware navigation: [`frontend/src/App.tsx`](../frontend/src/App.tsx).
- Model/schema/service map: [Module guide](modules.md).
- Live contracts: `/openapi.json`, `/docs`, `/redoc` on the API service.
- Persistence changes: add a migration in `backend/alembic/versions/`; validate it against the intended database. Startup upgrades all current Alembic heads.
- Image dependencies: `backend/requirements-api.txt` and `backend/requirements-worker.txt` drive separate images. Editing only `backend/requirements.txt` does not update those images.

## Logs and diagnosis

```bash
docker compose logs --tail=100 api worker
docker compose logs --tail=100 codex-sandbox
./scripts/status-dev.sh
```

Host logs and PID files are under `backend/logs/` and `frontend/logs/`. Inspect relevant logs locally and redact credentials and research content before sharing. For deployment failures use the [operator troubleshooting guide](deployment.md#troubleshooting).

## Contribution checklist

1. Follow `AGENTS.md`; prefer small diffs and existing module boundaries.
2. Use English identifiers, comments, documentation and Conventional Commit subjects. Put all UI text in en-US/zh-CN locale keys. Do not add emoji to source.
3. Add/update regression tests for behavior changes, validate request types, and enforce authorization server-side. Add indexes for foreign keys.
4. Preserve raw-data boundaries; do not add telemetry or external calls without explicit authorization. Review any new provider's data flow.
5. Run relevant tests, frontend checks when applicable, and pre-commit; report failures or skips explicitly.
6. Update current guides when behavior changes. Keep historical plans separate from current operating instructions.
7. Use a Conventional Commit PR title and describe behavior, validation, migration and deployment impacts. Follow repository branch conventions (`feat/`, `fix/`, `refactor/`, `docs/`) when choosing a new branch.
