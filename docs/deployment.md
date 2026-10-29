# Deploying OpenColab Core

This repository deploys the general research platform. It contains no antimicrobial peptide screening or vaccine design runtime, model installer, or domain database tables. See [architecture](architecture.md), [modules](modules.md), and [extraction notes](core-extraction.md).

## Prerequisites

- Docker with a recent Compose plugin supporting the overlay's `!override` tag.
- Host `curl` for startup checks.
- Sufficient disk for Python/PyTorch images, local embedding/OCR models, uploaded documents and database growth. Image builds and model acquisition need connectivity unless supplied from an offline mirror.
- A compatible local or explicitly configured cloud LLM endpoint. Codex tasks also require the configured wire API and authenticated sandbox runtime.

## 1. Configure

From the checkout root:

```bash
cp .env.template .env
```

Edit `.env` locally. Set `OPENCOLAB_SECRET_KEY`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `OPENCOLAB_ADMIN_PASSWORD` and `OPENCOLAB_CODEX_RUNTIME_API_KEY`. Use strong independent secrets; `openssl rand -hex 32` can generate a value. Never commit the populated file. The admin password seeds the first `admin` account and is not an ongoing password-reset mechanism.

Configure `OPENCOLAB_LLM_MODEL`, `OPENCOLAB_LLM_API_BASE` and any required API key. Local model endpoints must be reachable from the containers; host loopback is not container loopback. Runtime database settings and selected LLM profiles can override environment defaults: see [configuration](development.md#configuration).

Set `OPENCOLAB_EMBEDDING_LOCAL_MODEL_PATH` to a model directory available inside the worker (the host `models/` directory is mounted at `/models`). The default embedding provider is local, cloud fallback is `none`, and local-files-only loading is enabled. Obtain the model before starting document processing. Enable local marker only after preparing its model cache if scanned-document OCR is needed; basic PDF text extraction is used otherwise.

The supplied Compose file constructs API/worker database URLs from `POSTGRES_*`. Supplying only `OPENCOLAB_DATABASE_URL` does not replace those container credentials.

## 2. Select frontend mode and build

By default, Compose runs Vite against bind-mounted frontend source and enables API reload. For a built frontend served through nginx, set this in `.env` **before building**:

```dotenv
COMPOSE_FILE=docker-compose.yml:docker-compose.test.yml
```

Then build:

```bash
./scripts/docker-build.sh
```

The API and worker have separate dependency files: `backend/requirements-api.txt` and `backend/requirements-worker.txt`. The development union is `backend/requirements.txt`. Rebuild the relevant image after dependency changes.

## 3. Start and verify

```bash
./scripts/docker-start.sh
curl -fsS http://localhost:8431/api/v1/health
curl -fsS http://localhost:8430/api/v1/health
docker compose ps
docker compose logs --tail=100 api worker
```

The API entrypoint runs `alembic upgrade heads` before serving requests. Use a **fresh core database**: the core graph has removed domain migrations and is not an in-place upgrade path for an existing full-product database.

| Service | Host port | Purpose |
|---|---|---|
| `frontend` | 8430 | Vite or nginx UI |
| `api` | 8431 | FastAPI; `/docs`, `/redoc`, `/openapi.json` |
| `worker` | Not published | Document processing, bibliographic jobs and query embeddings |
| `postgres` | 8432 | PostgreSQL |
| `qdrant` | 8433 | Vector storage |
| `codex-sandbox` | 127.0.0.1:8434 | Authenticated Codex runtime |

Open `http://localhost:8430`, sign in as `admin` with the configured password, configure/test the active model profile, create a project, upload a small document and check processing/retrieval. Exercise a Codex task separately to verify its endpoint and shared workspace configuration.

## Host development

See [development](development.md) for the Python 3.12 virtual environment and Node setup. `scripts/start-dev.sh` starts dependency containers and API/worker/Vite host processes on 8000/8001/5173. It does not start the Codex sandbox and can stop processes occupying those ports. Do not run host and Compose application workers against the same database simultaneously.

## Offline deployment and data boundaries

Core has no universal offline toggle. Review every configured provider and installed skill before importing private data.

```dotenv
OPENCOLAB_PDF_PPS_ENABLED=false
OPENCOLAB_EMBEDDING_PROVIDER=local
OPENCOLAB_EMBEDDING_FALLBACK_PROVIDER=none
OPENCOLAB_EMBEDDING_LOCAL_FILES_ONLY=true
OPENCOLAB_BIBLIOGRAPHIC_LOOKUP_ENABLED=false
```

1. Preload images, dependencies, embedding/OCR weights and an appropriate local model endpoint before disconnecting the network.
2. Configure local model and workspace paths as seen inside the containers. Verify Codex wire API compatibility if tasks are required.
3. Keep remote OCR disabled. Enabling PPS with a URL and credentials uploads original PDF content; this conflicts with a deployment policy requiring raw files to remain local.
4. Keep cloud embedding fallback disabled. Cloud embeddings send text; cloud LLMs receive selected research context. Bibliographic lookups send identifiers. Skills can make calls according to their content and execution permissions.
5. Check effective runtime/profile settings, recreate services after environment changes, and test ingestion, retrieval, chat and tasks with outbound access blocked. Source code alone does not prove a deployment is air-gapped.

Remote PPS has no preset service URL in Core. Operators deliberately enabling it must provide their own endpoint. The original product's private service configuration and credentials are not migration inputs.

## Updates and stopping

```bash
git pull --ff-only
docker compose restart api worker
```

For dependencies or a built frontend, rebuild and recreate:

```bash
./scripts/docker-build.sh
docker compose up -d
```

Vite and the dev API reloader pick up source edits; workers always need a restart. nginx frontend changes require a rebuild. Compose/environment changes require recreation rather than merely restarting existing containers.

```bash
./scripts/docker-stop.sh
```

Normal stopping preserves volumes. `--volumes` deletes persistent database/vector volumes; do not use it as an update procedure.

## Backup and restore

Preserve a coordinated PostgreSQL dump, Qdrant snapshots, `uploads/`, `codex-workspace/`, uploaded `backend/skill-packs/`, model caches, sandbox state and protected deployment configuration. Record code/image versions and Alembic revisions. A database dump alone does not restore document files or retrieval state.

Stop writers for a coordinated maintenance backup. Use supported database/vector snapshot mechanisms; copying a live database directory is not a consistent backup. Keep credentials and research data in protected backup storage.

Restore to an isolated instance with matching code, schema, vectors and files first. Verify access controls, previews, retrieval and tasks before reopening traffic. The API auto-migrates on startup, so inspect migration compatibility before starting a restored installation. A code rollback alone is not a schema rollback; inspect downgrade support or restore the matching backup rather than applying a blind `downgrade -1`.

## Troubleshooting

| Symptom | Check |
|---|---|
| Compose fails to resolve configuration | Required `.env` keys and Compose support for `!override` |
| API exits on first start | Admin password, database connectivity and migration logs |
| Worker cannot embed a document | Local model files/path, dependency cache and effective provider settings |
| Scanned PDF has little text | Enable and provision local OCR; basic extraction does not perform equivalent OCR |
| Chat succeeds but tasks fail | Sandbox auth, model wire API compatibility and shared workspace paths |
| nginx/Vite switch fails | Rebuild under the intended `COMPOSE_FILE`; nginx listens on container port 80, Vite on 5173 |
| Migration references an unknown domain revision | A full-product database was used; deploy Core with a separate fresh database |
| Port already occupied | Existing product/dev stack; use a separate host or deliberate port mappings |

Logs: `docker compose logs api worker codex-sandbox`. Inspect locally and redact credentials and research content before sharing.
