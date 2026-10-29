#!/bin/bash
# Start both frontend and backend dev servers, then display access URLs.
# Run from opencolab/ directory. Use ./scripts/stop-dev.sh to stop.
#
# Adapts to various local environments:
#   - Auto-detects Python venv (or offers to create one)
#   - Works with docker compose (v2) or docker-compose (v1)
#   - Cross-platform port checking (lsof / fuser / ss fallback)
#   - Preflight checks for required tools with helpful error messages

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Prefer the user-installed Homebrew Node.js before older system Node.js.
if [ -d "$HOME/.brew/bin" ]; then
  export PATH="$HOME/.brew/bin:$PATH"
fi

# ── Configuration ──
BACKEND_PID_FILE="backend/logs/backend.pid"
WORKER_PID_FILE="backend/logs/worker.pid"
FRONTEND_PID_FILE="frontend/logs/frontend.pid"
BACKEND_URL="http://localhost:8000"
WORKER_URL="http://localhost:8001"
FRONTEND_URL="http://localhost:5173"
STARTUP_TIMEOUT=60
DOCKER_TIMEOUT=30
DOCKER_DEPS=(postgres qdrant)

# ── Output helpers ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'
error()   { printf "%bError:%b %s\n"    "$RED"    "$NC" "$*" >&2; }
warn()    { printf "%bWarning:%b %s\n"  "$YELLOW" "$NC" "$*" >&2; }
success() { printf "%b%s%b\n"           "$GREEN"  "$*" "$NC"; }
info()    { printf "%b%s%b\n"           "$BOLD"   "$*" "$NC"; }

# ═══════════════════════════════════════════════════════════════════
# Preflight: Check required tools
# ═══════════════════════════════════════════════════════════════════
preflight() {
  local missing=()

  command -v python3 >/dev/null 2>&1 || missing+=("python3 (Python 3.12+)")
  command -v node    >/dev/null 2>&1 || missing+=("node (Node.js)")
  command -v npm     >/dev/null 2>&1 || missing+=("npm")
  command -v curl    >/dev/null 2>&1 || missing+=("curl")

  if ! command -v docker >/dev/null 2>&1; then
    warn "docker not found — postgres/qdrant must be running externally"
  fi

  if [ "${#missing[@]}" -gt 0 ]; then
    error "Missing required tools:"
    for tool in "${missing[@]}"; do
      printf "  - %s\n" "$tool"
    done
    echo ""
    echo "Please install the missing tools and re-run."
    exit 1
  fi
}

# ═══════════════════════════════════════════════════════════════════
# Detect docker compose (v2 "docker compose" vs v1 "docker-compose")
# ═══════════════════════════════════════════════════════════════════
detect_docker_compose() {
  if docker compose version &>/dev/null; then
    echo "docker compose"
  elif command -v docker-compose >/dev/null 2>&1 && docker-compose version &>/dev/null; then
    echo "docker-compose"
  else
    echo ""
  fi
}

# ═══════════════════════════════════════════════════════════════════
# Find PIDs listening on a port — cross-platform
# ═══════════════════════════════════════════════════════════════════
find_port_pids() {
  local port="$1"
  local pids

  # macOS/BSD: lsof is built-in
  pids=$(lsof -ti ":$port" 2>/dev/null) && { printf '%s' "$pids"; return 0; }
  # Linux: fuser (from psmisc, commonly installed)
  pids=$(fuser "$port/tcp" 2>/dev/null | tr -d ' ') && [ -n "$pids" ] && { printf '%s' "$pids"; return 0; }
  # Linux: parse ss output
  if command -v ss >/dev/null 2>&1; then
    pids=$(ss -tlnp "sport = :$port" 2>/dev/null | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | sort -u)
    [ -n "$pids" ] && { printf '%s' "$pids"; return 0; }
  fi
  return 1
}

# ═══════════════════════════════════════════════════════════════════
# Detect Python environment (venv, conda, system)
# ═══════════════════════════════════════════════════════════════════
detect_python_env() {
  # 1. Documented venv path
  if [ -f "backend/.venv/bin/activate" ]; then
    printf 'venv:%s' "$ROOT/backend/.venv/bin/activate"
    return 0
  fi

  # 2. Alternative venv paths
  for venv_path in ".venv/bin/activate" "backend/venv/bin/activate" "venv/bin/activate"; do
    if [ -f "$venv_path" ]; then
      printf 'venv:%s' "$ROOT/$venv_path"
      return 0
    fi
  done

  # 3. Already inside an activated virtualenv
  if [ -n "${VIRTUAL_ENV:-}" ] && [ -f "$VIRTUAL_ENV/bin/activate" ]; then
    printf 'active:%s' "$VIRTUAL_ENV"
    return 0
  fi

  # 4. Conda environment (non-base) — verify all critical packages are installed
  if command -v conda >/dev/null 2>&1 && [ -n "${CONDA_DEFAULT_ENV:-}" ] && [ "$CONDA_DEFAULT_ENV" != "base" ]; then
    if python3 -c "import fastapi, uvicorn, alembic, jose, qdrant_client, sqlalchemy, asyncpg" 2>/dev/null; then
      printf 'conda:%s' "$CONDA_DEFAULT_ENV"
      return 0
    fi
    warn "conda environment '$CONDA_DEFAULT_ENV' is active, but required Python packages are not installed."
    echo "  Install them with: conda install fastapi uvicorn alembic sqlalchemy asyncpg qdrant-client python-jose"
    echo "  Or let the script create a project venv: python3 -m venv backend/.venv && pip install -r backend/requirements.txt"
    echo ""
    return 1  # Trigger setup_venv — conda env lacks required packages
  fi

  # 5. System python3 with all critical packages installed
  if python3 -c "import fastapi, uvicorn, alembic, jose, qdrant_client, sqlalchemy, asyncpg" 2>/dev/null; then
    printf 'system'
    return 0
  fi

  return 1
}

# ═══════════════════════════════════════════════════════════════════
# Interactive venv setup (only when terminal is attached)
# ═══════════════════════════════════════════════════════════════════
setup_venv() {
  echo ""
  info "Python virtual environment not found."
  echo ""
  echo "OpenColab requires Python 3.12+ with dependencies installed."
  echo ""
  echo "Quick setup:"
  echo "  cd backend"
  echo "  python3 -m venv .venv"
  echo "  source .venv/bin/activate"
  echo "  pip install -r requirements.txt"
  echo "  cd .."
  echo ""

  if [ ! -t 0 ]; then
    error "Non-interactive terminal — set up the venv manually and re-run."
    exit 1
  fi

  printf "Create venv now? [Y/n] "
  read -r reply
  reply="${reply:-Y}"
  if [[ ! "$reply" =~ ^[Yy] ]]; then
    error "Cannot proceed without a Python environment."
    exit 1
  fi

  echo ""
  info "Creating virtual environment at backend/.venv ..."
  (cd backend && python3 -m venv .venv) || {
    error "Failed to create venv. Check that python3 is Python 3.12+."
    exit 1
  }

  echo "Installing Python dependencies (this may take a few minutes)..."
  (cd backend && source .venv/bin/activate && pip install -r requirements.txt) || {
    warn "pip install encountered errors."
    echo "  You may need to install system build dependencies first."
    echo "  See backend/requirements.txt for details."
    exit 1
  }
  success "Virtual environment ready."
}

# ═══════════════════════════════════════════════════════════════════
# Check .env file exists and has required settings
# ═══════════════════════════════════════════════════════════════════
check_env_file() {
  if [ ! -f ".env" ]; then
    error ".env file not found."
    echo ""
    echo "Create one from the template:"
    echo "  cp .env.template .env"
    echo ""
    echo "Then edit .env and set at minimum:"
    echo "  OPENCOLAB_SECRET_KEY=<random-string>"
    echo "  OPENCOLAB_ADMIN_PASSWORD=<your-password>"
    echo "  POSTGRES_USER=<your-db-user>"
    echo "  POSTGRES_PASSWORD=<your-db-password>"
    exit 1
  fi

  # Parse a .env variable value (handles quoted and unquoted values)
  _env_val() {
    sed -n "s/^${1}=//p" .env | sed 's/^["'"'"']\(.*\)["'"'"']$/\1/' | head -1
  }

  local db_url pg_user pg_pass admin_pw issues=()

  db_url=$(_env_val 'OPENCOLAB_DATABASE_URL')
  pg_user=$(_env_val 'POSTGRES_USER')
  pg_pass=$(_env_val 'POSTGRES_PASSWORD')
  admin_pw=$(_env_val 'OPENCOLAB_ADMIN_PASSWORD')

  # Database credentials: OPENCOLAB_DATABASE_URL OR (POSTGRES_USER + POSTGRES_PASSWORD)
  if [ -z "$db_url" ] && { [ -z "$pg_user" ] || [ -z "$pg_pass" ]; }; then
    issues+=("Database credentials not set. Set either OPENCOLAB_DATABASE_URL or both POSTGRES_USER + POSTGRES_PASSWORD")
  fi

  # Admin password (required on first run; backend check is lenient if admin already exists)
  if [ -z "$admin_pw" ]; then
    issues+=("OPENCOLAB_ADMIN_PASSWORD is empty (required for first-run admin account seeding)")
  fi

  # Secret key (warn only, backend has a default)
  if grep -q "^OPENCOLAB_SECRET_KEY=change-me-in-production" .env 2>/dev/null; then
    warn "OPENCOLAB_SECRET_KEY is still the default placeholder."
    echo "  Set a strong random key in .env before exposing this to a network."
  fi

  if [ "${#issues[@]}" -gt 0 ]; then
    error "Required settings missing in .env:"
    for msg in "${issues[@]}"; do
      printf "  - %s\n" "$msg"
    done
    echo ""
    echo "Edit .env (copy from .env.template if needed) and set these values."
    exit 1
  fi
}

# ═══════════════════════════════════════════════════════════════════
# Check if servers are already running
# ═══════════════════════════════════════════════════════════════════
check_already_running() {
  local running=0
  for pid_file in "$BACKEND_PID_FILE" "$FRONTEND_PID_FILE" "$WORKER_PID_FILE"; do
    if [ -f "$pid_file" ]; then
      local pid
      pid=$(cat "$pid_file")
      if kill -0 "$pid" 2>/dev/null; then running=1; fi
    fi
  done
  if [ "$running" = 1 ]; then
    error "Dev servers already running. Use ./scripts/stop-dev.sh to stop first."
    echo ""
    echo "  Frontend: $FRONTEND_URL"
    echo "  Backend:  $BACKEND_URL"
    echo "  Worker:   $WORKER_URL"
    exit 1
  fi
}

# ═══════════════════════════════════════════════════════════════════
# Prevent local app processes from competing with Docker app services
# ═══════════════════════════════════════════════════════════════════
check_conflicting_docker_app_services() {
  local dc="$1"
  local app_services=(frontend api worker)
  local running_services=()

  for svc in "${app_services[@]}"; do
    local state
    state=$($dc ps --format '{{.Service}} {{.State}}' 2>/dev/null | awk -v s="$svc" '$1==s{print $2}')
    if [ "$state" = "running" ]; then
      running_services+=("$svc")
    fi
  done

  if [ "${#running_services[@]}" -eq 0 ]; then
    return 0
  fi

  error "Docker application services are already running: ${running_services[*]}"
  echo ""
  echo "Starting local application services at the same time can create duplicate workers"
  echo "that compete for the same processing tasks. Choose one application mode:"
  echo ""
  echo "  Docker mode: keep using the running Compose services."
  echo "  Local mode:  $dc stop frontend api worker"
  echo "               ./scripts/start-dev.sh"
  exit 1
}

# ═══════════════════════════════════════════════════════════════════
# Ensure Docker dependency services are running
# ═══════════════════════════════════════════════════════════════════
start_docker_deps() {
  local dc="$1"
  local needs_start=()

  for svc in "${DOCKER_DEPS[@]}"; do
    local state
    state=$($dc ps --format '{{.Service}} {{.State}}' 2>/dev/null | awk -v s="$svc" '$1==s{print $2}')
    if [ "$state" != "running" ]; then
      needs_start+=("$svc")
    fi
  done

  if [ "${#needs_start[@]}" -eq 0 ]; then
    return 0
  fi

  echo "Starting Docker services: ${needs_start[*]}..."
  $dc up -d "${needs_start[@]}"

  local elapsed=0 all_up=0
  while [ "$elapsed" -lt "$DOCKER_TIMEOUT" ]; do
    all_up=1
    for svc in "${needs_start[@]}"; do
      state=$($dc ps --format '{{.Service}} {{.State}}' 2>/dev/null | awk -v s="$svc" '$1==s{print $2}')
      if [ "$state" != "running" ]; then all_up=0; break; fi
    done
    [ "$all_up" = 1 ] && break
    sleep 2
    elapsed=$((elapsed + 2))
  done

  if [ "$all_up" != 1 ]; then
    error "Docker services failed to start within ${DOCKER_TIMEOUT}s."
    echo "  Run '$dc ps' to diagnose."
    exit 1
  fi
  success "Docker services ready."
}

# ═══════════════════════════════════════════════════════════════════
# Clean up orphan processes on dev ports (best-effort)
# ═══════════════════════════════════════════════════════════════════
cleanup_orphan_ports() {
  for port in 8000 8001 5173; do
    local pids
    pids=$(find_port_pids "$port" 2>/dev/null) || continue
    if [ -n "$pids" ]; then
      echo "Cleaning up orphan process(es) on port $port (PIDs: $pids)..."
      for p in $pids; do kill "$p" 2>/dev/null || true; done
      sleep 1
    fi
  done
}

# ═══════════════════════════════════════════════════════════════════
# Wait for services to be healthy
# ═══════════════════════════════════════════════════════════════════
wait_for_services() {
  local backend_ok=0 worker_ok=0 frontend_ok=0 backend_failed=0 elapsed=0
  local SPINNER='|/-\'
  local BACKEND_STARTUP_LOG="backend/logs/startup.log"
  local backend_log_start
  backend_log_start=$(wc -l < "$BACKEND_STARTUP_LOG" 2>/dev/null || echo 0)

  while [ "$elapsed" -lt "$STARTUP_TIMEOUT" ]; do
    # Check for fatal backend startup error
    if [ "$backend_ok" = 0 ] && [ "$backend_failed" = 0 ]; then
      if tail -n +"$backend_log_start" "$BACKEND_STARTUP_LOG" 2>/dev/null | grep -q "Application startup failed"; then
        backend_failed=1
        printf '\r%80s\r' ''
        error "Backend failed to start."
        local last_err
        last_err=$(grep -E 'ERROR|Exception|Error' backend/logs/app.log 2>/dev/null | tail -3)
        [ -n "$last_err" ] && printf '%s\n' "$last_err" | sed 's/^/  /'
        echo "  See backend/logs/app.log for full details."
        exit 1
      fi
    fi

    [ "$backend_ok"  = 0 ] && curl -s --max-time 2 -o /dev/null -w "%{http_code}" "$BACKEND_URL/api/v1/health" 2>/dev/null | grep -q 200 && backend_ok=1
    [ "$worker_ok"   = 0 ] && curl -s --max-time 2 -o /dev/null -w "%{http_code}" "$WORKER_URL/health" 2>/dev/null | grep -q 200 && worker_ok=1
    [ "$frontend_ok" = 0 ] && curl -s --max-time 2 -o /dev/null -w "%{http_code}" "$FRONTEND_URL" 2>/dev/null | grep -qE '200|304' && frontend_ok=1

    [ "$backend_ok" = 1 ] && [ "$frontend_ok" = 1 ] && break

    local spin_char be_status wk_status fe_status
    spin_char="${SPINNER:$((elapsed % 4)):1}"
    be_status="waiting"; [ "$backend_ok"  = 1 ] && be_status="ready"
    wk_status="loading"; [ "$worker_ok"   = 1 ] && wk_status="ready"
    fe_status="waiting"; [ "$frontend_ok" = 1 ] && fe_status="ready"

    local bar_filled bar_empty bar
    bar_filled=$(( (elapsed * 20) / STARTUP_TIMEOUT ))
    bar_empty=$(( 20 - bar_filled ))
    bar="["
    local i=0; while [ "$i" -lt "$bar_filled" ]; do bar="${bar}#"; i=$((i+1)); done
    i=0; while [ "$i" -lt "$bar_empty"  ]; do bar="${bar}."; i=$((i+1)); done
    bar="${bar}]"

    printf '\r  %s %s %ds/%ds  backend: %-7s  worker: %-7s  frontend: %-7s' \
      "$spin_char" "$bar" "$elapsed" "$STARTUP_TIMEOUT" "$be_status" "$wk_status" "$fe_status"
    sleep 1
    elapsed=$((elapsed + 1))
  done
  printf '\r%80s\r' ''

  if [ "$backend_ok" = 0 ] || [ "$frontend_ok" = 0 ]; then
    warn "Startup timed out after ${STARTUP_TIMEOUT}s."
    [ "$backend_ok"  = 0 ] && echo "  Backend not ready  — see backend/logs/startup.log and backend/logs/app.log"
    [ "$frontend_ok" = 0 ] && echo "  Frontend not ready — see frontend/logs/startup.log"
    [ "$worker_ok"   = 0 ] && echo "  Worker still loading (models may be downloading — this is normal on first run)"
  fi

  # Return status via global vars for the summary
  BACKEND_OK=$backend_ok
  WORKER_OK=$worker_ok
  FRONTEND_OK=$frontend_ok
}

# ═══════════════════════════════════════════════════════════════════
# Print startup summary
# ═══════════════════════════════════════════════════════════════════
print_summary() {
  echo ""
  success "OpenColab dev servers"
  echo "=========================================="
  echo ""
  printf "  Frontend:  %s  %s\n" "$FRONTEND_URL" "$([ "$FRONTEND_OK" = 1 ] && echo '(ready)' || echo '(starting...)')"
  printf "  Backend:   %s  %s\n" "$BACKEND_URL"  "$([ "$BACKEND_OK"  = 1 ] && echo '(ready)' || echo '(starting... or check postgres/qdrant)')"
  printf "  Worker:    %s  %s\n" "$WORKER_URL"   "$([ "$WORKER_OK"   = 1 ] && echo '(ready)' || echo '(loading models — may take 1-2 min on first run)')"
  echo ""
  echo "  Logs:      backend/logs/app.log  backend/logs/worker.log  frontend/logs/dev.log"
  echo "  Stop:      ./scripts/stop-dev.sh"
  echo ""
}

# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

echo ""
info "OpenColab — Starting Development Servers"
echo "=========================================="
echo ""

# 1. Preflight checks
preflight

# 2. Validate .env file
check_env_file

# 3. Detect and activate Python environment
PYTHON_ENV=$(detect_python_env) || setup_venv
PYTHON_ENV=$(detect_python_env) || { error "Python environment still not detected after setup."; exit 1; }

case "${PYTHON_ENV%%:*}" in
  venv)   source "${PYTHON_ENV#*:}" || { error "Failed to activate venv: ${PYTHON_ENV#*:}"; exit 1; } ;;
  active) ;;  # already in an activated virtualenv
  conda)  ;;  # conda is already active
  system) ;;  # using system python, packages should be on PATH
  *)
    error "Unknown Python environment type: ${PYTHON_ENV%%:*}"
    exit 1
    ;;
esac

# Verify critical packages are importable after activation
if ! python3 -c "import fastapi, uvicorn, alembic, jose, qdrant_client, sqlalchemy, asyncpg" 2>/dev/null; then
  warn "Some Python packages are missing or broken in the current environment."
  echo "  Reinstalling from requirements.txt..."
  (cd backend && pip install -r requirements.txt) || {
    error "pip install failed. Check the output above for details."
    exit 1
  }
fi

# 4. Check not already running
check_already_running

# 5. Docker dependency services
DOCKER_COMPOSE=$(detect_docker_compose)
if [ -n "$DOCKER_COMPOSE" ]; then
  check_conflicting_docker_app_services "$DOCKER_COMPOSE"
  start_docker_deps "$DOCKER_COMPOSE"
else
  warn "Docker Compose not found."
  echo "  Make sure PostgreSQL and Qdrant are running and accessible."
  echo "  See .env for connection settings (expected ports: PG=8432, Qdrant=8433)."
  echo ""
fi

# 6. Kill orphan processes on dev ports (best-effort, cross-platform)
cleanup_orphan_ports

# 7. Create log directories
mkdir -p backend/logs frontend/logs

# 8. Environment variables
export OPENCOLAB_ENV="${OPENCOLAB_ENV:-dev}"
export OPENCOLAB_UPLOAD_DIR="${OPENCOLAB_UPLOAD_DIR:-$ROOT/uploads}"
mkdir -p "$OPENCOLAB_UPLOAD_DIR"

# 9. Database migrations
echo "Running database migrations..."
(cd backend && PYTHONPATH=. alembic upgrade heads) || {
  error "Database migration failed."
  echo "  Check that PostgreSQL is running and .env credentials are correct."
  exit 1
}
success "Migrations complete."

# 10. Start backend
echo "Starting backend..."
(
  cd backend
  nohup env PYTHONPATH=. OPENCOLAB_ENV="$OPENCOLAB_ENV" OPENCOLAB_UPLOAD_DIR="$OPENCOLAB_UPLOAD_DIR" \
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 >> logs/startup.log 2>&1 &
  echo $! > logs/backend.pid
)

# 11. Start worker
echo "Starting worker..."
(
  cd backend
  nohup env PYTHONPATH=. OPENCOLAB_ENV="$OPENCOLAB_ENV" OPENCOLAB_UPLOAD_DIR="$OPENCOLAB_UPLOAD_DIR" \
    python -m app.worker.main >> logs/worker.log 2>&1 &
  echo $! > logs/worker.pid
)

# 12. Start frontend (run npm install if needed)
echo "Starting frontend..."
if [ ! -d "frontend/node_modules" ]; then
  echo "  Installing frontend dependencies (npm install)..."
  (cd frontend && npm install) || {
    error "npm install failed. Check frontend/logs/startup.log for details."
    exit 1
  }
fi
(cd frontend && nohup env OPENCOLAB_ENV="$OPENCOLAB_ENV" npm run dev >> logs/startup.log 2>&1 &)

# 13. Wait for services
BACKEND_OK=0 WORKER_OK=0 FRONTEND_OK=0
wait_for_services

# 14. Summary
print_summary
