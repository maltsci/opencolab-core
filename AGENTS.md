# AGENTS.md

This file provides guidance to all Coding Agents (Claude Code, Codex, etc.) working with code in this repository.

## Project Overview

OpenColab Core is a **local-first AI research copilot** targeting scientists who need privacy, usability, and domain expertise. Its core value proposition is breaking the tradeoff between data security (local) and AI capability (cloud). The system is designed to run fully air-gapped.

The current focus is the **Discovery Loop** (MVP): literature retrieval, contradiction mining, gap identification, and hypothesis generation. The Solution Loop (experiment execution) is deferred to a future phase.

Target users: PIs, Researchers, and System Administrators in academic labs.

## Tech Stack

### Frontend (`frontend/`)
- **Language**: TypeScript
- **Framework**: React
- **UI Library**: Ant Design
- **Data Fetching**: React Query
- **i18n**: en-US and zh-CN

### Backend (`backend/`)
- **Language**: Python 3.10+
- **Framework**: FastAPI
- **Agent Orchestration**: LangGraph
- **Schema & Validation**: Pydantic V2
- **Protocol**: MCP (Model Context Protocol)
- **LLM Gateway**: LiteLLM (supports OpenAI-compatible APIs and local Ollama)
- **Database**: PostgreSQL
- **Vector Store**: Qdrant
- **Embedding**: bge-m3 (local, switchable to API)
- **Document Parsing**: marker (PDF), python-docx (Word), plain-text reader (Markdown/TXT)
- **Skills**: SKILL.md packages (skill packs) uploaded by admins, versioned, executed autonomously in the codex sandbox. The legacy declarative skill/workflow-definition system was removed; extensibility = skill packs only. Uploaded packs live in `backend/skill-packs/` (gitignored).

### Communication
- RESTful API: `/api/v1/{resource}`
- WebSocket: streaming LLM responses
- Pagination: cursor-based

## Data Privacy Rule

**Raw data and PDFs MUST NEVER leave the local machine.** Only pre-processed chunks (text segments and embeddings) may be sent to cloud LLMs when the user explicitly opts into hybrid mode. By default, all processing — PDF parsing, chunking, embedding, vector storage, and optionally LLM inference — runs entirely on-premises. The system MUST support fully air-gapped (offline) deployment.

## Configuration

### Configuration Priority

Runtime settings are resolved in this order (highest to lowest priority):

1. **Database** (`system_configs` table) — set via Admin UI at `/admin/settings`, always wins
2. **Environment variables** (e.g. `OPENCOLAB_LLM_MODEL`)
3. **`.env.{environment}` file** (e.g. `.env.dev`, `.env.prod`)
4. **`.env` file** — base defaults, lowest priority

A value is used from the highest-priority source where it is set. If a key is absent at one level, resolution falls through to the next.

**Bootstrap settings** (database URL, secret key, Qdrant connection) can only be set via environment variables or `.env` file — they cannot be changed at runtime through the UI.

**Runtime settings** (LLM model, API key, embedding model, RAG parameters, file storage) can be managed through the Admin UI. Changes take effect immediately without restart.

**LLM API Key precedence**: If `OPENCOLAB_LLM_API_KEY` is set (via DB, env, or `.env`), it is passed explicitly to LiteLLM and overrides provider-specific env vars (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.). When `OPENCOLAB_LLM_API_KEY` is empty, LiteLLM auto-detects the provider key from environment variables.

### Environment Files

| File | Purpose | Git |
|---|---|---|
| `.env.template` | Template with all variables and comments | Committed |
| `.env.example` | Minimal example for quick start | Committed |
| `.env` | Active config (loaded by default) | **Ignored** |
| `.env.dev` | Local development overrides | **Ignored** |
| `.env.uat` | UAT environment overrides | **Ignored** |
| `.env.prod` | Production environment overrides | **Ignored** |

Copy `.env.template` to `.env.{your-environment}` and edit the values. The app loads `.env` then `.env.{OPENCOLAB_ENV}` (defaults to `dev`). For other environments, set `OPENCOLAB_ENV=uat` or `OPENCOLAB_ENV=prod`.

### First-Time Setup

On first admin login, a banner prompts the admin to configure LLM settings via the Admin > System Settings page. Alternatively, copy `.env.template` to `.env` and edit the values before starting.

## Development Commands

### Docker Compose (Full Stack)

See `docs/deployment.md` for installation and offline model preparation.

```bash
# Copy env file and set your secret key
cp .env.template .env
# Edit .env: OPENCOLAB_SECRET_KEY, POSTGRES_USER, POSTGRES_PASSWORD,
# OPENCOLAB_ADMIN_PASSWORD (seeds the admin account on first run) and
# OPENCOLAB_CODEX_RUNTIME_API_KEY (Compose refuses to resolve without it).

./scripts/docker-build.sh          # api, worker, frontend
./scripts/docker-start.sh          # starts the core platform
docker compose logs -f api worker  # service names are api/worker, not backend
./scripts/docker-stop.sh
```

The published host ports are 8430 (frontend), 8431 (api), 8432 (postgres), 8433
(qdrant), and 127.0.0.1:8434 (codex sandbox). Both compose and host-process mode
share the same postgres and qdrant, so two workers would poll one run queue - run
one mode at a time.

The compose stack has two frontends, chosen by one line in `.env`. Without
`COMPOSE_FILE` it runs the Vite dev server with `./frontend` bind-mounted and
uvicorn `--reload`, so source edits are live with no command. On a host that must
serve a build instead, set `COMPOSE_FILE=docker-compose.yml:docker-compose.test.yml`
(nginx on 80, reloader off); the two use different image names, so switching modes
recreates the container without needing `--build`. `docker-start.sh` prints which
mode it resolved.

### Local Backend Development

```bash
# 1. Start dependency services (PostgreSQL + Qdrant)
docker-compose up -d postgres qdrant

# 2. Set up Python environment
cd backend
python3.12 -m venv .venv   # Python 3.12 required (3.14 not yet supported by pydantic-core)
source .venv/bin/activate
pip install -r requirements.txt

# IMPORTANT: All Python packages MUST be installed in the project venv (backend/.venv), never globally.
# Always activate the venv first: source backend/.venv/bin/activate

# 3. Set environment variables (copy .env.template to .env and edit)
# Required: POSTGRES_USER, POSTGRES_PASSWORD (or OPENCOLAB_DATABASE_URL)
export OPENCOLAB_SECRET_KEY="your-secret-key"
export POSTGRES_USER="your-db-user"
export POSTGRES_PASSWORD="your-db-password"
export OPENCOLAB_QDRANT_HOST="localhost"

# 4. Run database migrations
PYTHONPATH=. alembic upgrade head

# 5. Start dev server (auto-reload)
PYTHONPATH=. uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Default admin account seeded on first run with username `admin` and the password set in `OPENCOLAB_ADMIN_PASSWORD`. The app will exit with an error if this variable is not set on the first run.

Backend logs are written to `backend/logs/app.log` (rotating, 10 MB, 5 backups). When the dev server starts, its process ID is written to `backend/logs/backend.pid` for status checks and graceful shutdown. Log timestamps: **dev** = local timezone, **other envs** = UTC (consistent with frontend).

### Local Frontend Development

```bash
cd frontend

# Install dependencies
npm install

# Start dev server (Vite proxies /api to localhost:8000)
npm run dev

# Production build
npm run build
```

The Vite dev server runs on `http://localhost:5173` and proxies all `/api` requests to the backend at `http://localhost:8000`.

Frontend logs are written to `frontend/logs/dev.log` (rotating, 10 MB, 5 backups). When the dev server starts, its process ID is written to `frontend/logs/frontend.pid` for status checks and graceful shutdown. Log timestamps: **dev** = local timezone, **other envs** = UTC (consistent with backend).

### Start / Check Status / Stop Dev Servers

```bash
# From opencolab/
./scripts/start-dev.sh    # Start both frontend and backend, show access URLs
./scripts/status-dev.sh   # Check if frontend and backend are running
./scripts/stop-dev.sh     # Stop both by killing processes from PID files
```

### Viewing Logs

Use [lnav](https://lnav.org/) to view both log files together with syntax highlighting, filtering, and search:

```bash
# Install (one-time)
brew install lnav

# View both frontend and backend logs
lnav frontend/logs/dev.log backend/logs/app.log
```

### Running Tests

```bash
# From the repository root
pip install -r backend/requirements-dev.txt  # if not already installed
pytest                                    # runs all tests
pytest tests/test_auth.py                 # run a specific test file
pytest -v                                 # verbose output
```

Tests use SQLite (aiosqlite) in-memory database. No external services required.

### Pre-commit and Pre-push Hooks

```bash
# Install (one-time, use project venv)
backend/.venv/bin/pip install pre-commit
pre-commit install
pre-commit install --hook-type pre-push   # Run tests before each push

# Run on modified files
pre-commit run

# Run on all files
pre-commit run --all-files
```

**Pre-push** (optional, disabled by default): Run `cp scripts/pre-push .git/hooks/pre-push && chmod +x .git/hooks/pre-push` to run tests before each push.

## Architecture

The system models research as two interlocking loops:

- **Discovery Loop** (current MVP focus): Extract hypotheses from information. Agents scan literature, mine contradictions and gaps, generate and evaluate hypotheses. Think "Research Detective."
- **Solution Loop** (future): Verify hypotheses through experiment. Agents plan SOPs, execute code, analyze data, validate results.

### Core Modules

- **Project-Centric Workspace**: Multi-tenant, project-isolated architecture with independent knowledge bases and conversation histories per project
- **Human-in-the-Loop Engine**: Dual conversation modes (fast/intuitive and slow/deliberate), visualized execution plans, checkpoint/approval mechanisms at critical nodes
- **Progressive Usability**: 90% of tasks via natural language chat; 10% via visible, interruptible execution plans; preset skills (literature summarization, translation, statistics) and advanced custom tool mode
- **Local-First Infrastructure**: PDF parsing, vector storage, and optional LLM inference all run on-premises; supports fully air-gapped operation

### User Roles

- **Researcher**: Creates tools/skills, asks questions, manages private data
- **PI/Lab Director**: Creates projects, manages skill libraries and data sources, oversees team
- **System Admin**: Installs and maintains the system, manages LLM API keys and users

## Development Workflow

### Branch Naming

- Feature: `feat/description-of-feature`
- Bug fix: `fix/description-of-fix`
- Refactor: `refactor/description`
- Documentation: `docs/description`

### Pull Request Checklist

- [ ] Code follows project conventions
- [ ] Pre-commit hooks pass
- [ ] Tests added/updated and passing
- [ ] Database migrations created if needed
- [ ] Documentation updated if needed
- [ ] PR title follows Conventional Commits
- [ ] No hardcoded strings (use i18n)
- [ ] No secrets in code

### Deployment Process

1. Merge to main branch
2. CI/CD runs tests and builds
3. Deploy to staging environment
4. Run smoke tests
5. Deploy to production

## Performance Guidelines

### Database Optimization

- **Always index foreign keys**: Add `index=True` to all `_bid` columns
- **Use batch operations**: Prefer bulk inserts/updates
- **Limit query results**: Use pagination for large datasets
- **Avoid N+1 queries**: Use joins or eager loading
- **Cache frequently accessed data**: Use Redis for hot data

### API Performance

- **Response time targets**: <200ms for reads, <500ms for writes
- **Pagination**: Default 20 items, max 100 items per page
- **Use async where appropriate**: For I/O bound operations
- **Implement rate limiting**: Protect against abuse
- **Add request timeouts**: Default 30s timeout

### Frontend Performance

- **Code splitting**: Lazy load routes and heavy components
- **Image optimization**: Use appropriate formats and sizes
- **Bundle size**: Keep main bundle <500KB
- **Cache API responses**: Use React Query or SWR
- **Debounce user input**: For search and filters

## Code Quality

### General Requirements

- Never use emoji in any source code

### Language Requirements

**English-Only Policy for Code**: All code-related content MUST be written in English to ensure consistency, maintainability, and international collaboration.

#### What MUST be in English

- **Code Comments**: All inline comments, block comments, and documentation comments
- **Variable and Function Names**: All identifiers in the code
- **Database Elements**: Table names, column names, and database comments
- **Constants and Enums**: All constant values and enumeration names
- **Log Messages and Debug Output**: All logging statements and debug information
- **Error Messages in Code**: Internal error messages and exception messages
- **Configuration Keys**: All configuration file keys and environment variable names
- **Git Commit Messages and PR Titles**: MUST use Conventional Commits format
- **Code Documentation**: README files, API documentation, code architecture docs

#### Exceptions to English-Only Policy

- **User-Facing Text**: All text for the UI must use i18n keys. The translation files (e.g., `en-US.json`, `zh-CN.json`) will naturally contain non-English text.
- **Test Data**: Test data can be in any language, especially for testing internationalization features.
- **Clarifying Comments**: For complex, region-specific business logic, a non-English comment can be added *after* the English one for extra clarity. Example: `# Check for valid ID card (检查身份证有效性)`

#### Conventional Commits Format

**Required Format**: `<type>: <description>` (e.g., `fix: resolve database connection timeout issue`)

**Common Types**:

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation
- `refactor:` - Code refactoring
- `test:` - Tests
- `chore:` - Maintenance
- `build:` - Build system or dependencies
- `ci:` - CI configuration
- `perf:` - Performance improvements
- `style:` - Formatting (no code change)
- `revert:` - Revert a previous commit

**Style Rules**:

- Type must be lowercase
- Use imperative mood ("add", not "added")
- Keep subject line ≤72 characters
- No trailing period
- English only

### Pre-commit Hooks

- **ALWAYS run pre-commit before committing code**: This ensures code quality and consistency
- For modified files only: `pre-commit run`
- For all files: `pre-commit run --all-files`
- If pre-commit is not installed, install it with: `pip install pre-commit && pre-commit install`
- Pre-commit will automatically check:
  - Code formatting
  - Linting issues
  - Type errors
  - Other code quality checks

## UI Development Guidelines

- **ALL user-facing strings MUST use i18n**: Never hardcode any text that will be displayed to users
- Use translation keys instead of hardcoded strings
- Examples:
  - Correct: `t('errors.no-permission')`
  - Wrong: `'您当前没有权限访问此内容'`
  - Correct: `t('common.retry', 'Retry')` (with fallback)
  - Wrong: `'重试'`
- The frontend language list shows only `en-US` and `zh-CN`.

### File and Directory Naming Conventions

#### Directory Naming

- **Use kebab-case (lowercase with hyphens)** for all directories
- Examples:
  - Correct: `user-profile/`, `auth-components/`, `api-utils/`
  - Wrong: `userProfile/`, `AuthComponents/`, `apiUtils/`

#### File Naming

- **Component files**: Use PascalCase (e.g., `UserProfile.tsx`, `NavBar.tsx`)
- **Regular TypeScript/JavaScript files**: Use kebab-case (e.g., `api-utils.ts`, `auth-helper.ts`)
- **CSS/SCSS files**: Use kebab-case (e.g., `global-styles.css`)
- **CSS Modules**: Match component name (e.g., `UserProfile.module.scss`)
- **Test files**: Match the file being tested with `.test.ts` or `.spec.ts` suffix
- **Type definition files**: Use kebab-case with `.d.ts` extension
- **Configuration files**: Use lowercase with dots (e.g., `.eslintrc.json`)
