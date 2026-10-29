#!/bin/bash
# Start OpenColab via Docker Compose.
# Run from the opencolab/ directory: ./scripts/docker-start.sh
#
# Prerequisites:
#   - Docker and Docker Compose installed
#   - .env file exists (copy .env.template to .env and edit)
#   - Images built with ./scripts/docker-build.sh (or let this script build them)
#
# Options:
#   --build    Rebuild images before starting

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BUILD_FLAG=""
for arg in "$@"; do
  case "$arg" in
    --build) BUILD_FLAG="--build" ;;
    *)
      echo "Unknown option: $arg"
      echo "Usage: $0 [--build]"
      exit 1
      ;;
  esac
done

# ── Validate .env file ──
if [ ! -f ".env" ]; then
  echo "Error: .env file not found."
  echo ""
  echo "Create one from the template:"
  echo "  cp .env.template .env"
  echo "  # Then edit .env and set OPENCOLAB_SECRET_KEY, POSTGRES_PASSWORD, etc."
  exit 1
fi

# Parse a .env variable value (handles quoted and unquoted values)
_env_val() {
  sed -n "s/^${1}=//p" .env | sed 's/^["'"'"']\(.*\)["'"'"']$/\1/' | head -1
}

db_url=$(_env_val 'OPENCOLAB_DATABASE_URL')
pg_user=$(_env_val 'POSTGRES_USER')
pg_pass=$(_env_val 'POSTGRES_PASSWORD')

issues=""
if [ -z "$db_url" ] && { [ -z "$pg_user" ] || [ -z "$pg_pass" ]; }; then
  issues="${issues}  - Database credentials not set. Set either OPENCOLAB_DATABASE_URL or both POSTGRES_USER + POSTGRES_PASSWORD\n"
fi

if [ -n "$issues" ]; then
  echo "Error: Required settings missing in .env:"
  printf "%b" "$issues"
  echo ""
  echo "Edit .env and set these values, then re-run."
  exit 1
fi

# Warn if secret key has not been changed
if grep -q "^OPENCOLAB_SECRET_KEY=change-me-in-production" .env; then
  echo "Warning: OPENCOLAB_SECRET_KEY is still set to the default placeholder."
  echo "         Edit .env and set a strong secret key before exposing this to a network."
  echo ""
fi

# The admin seed exits the process when this is empty and the users table is
# still empty, so a first run would look like a slow start instead of a
# misconfiguration. An existing deployment may legitimately blank it afterwards.
if [ -z "$(_env_val 'OPENCOLAB_ADMIN_PASSWORD')" ]; then
  echo "Warning: OPENCOLAB_ADMIN_PASSWORD is empty in .env."
  echo "         A fresh database will refuse to seed the admin user and the api"
  echo "         container will exit. Set it before the first start; it can be"
  echo "         removed again once the admin account exists."
  echo ""
fi

api_port=$(_env_val 'API_PORT'); api_port="${api_port:-8431}"
frontend_port=$(_env_val 'FRONTEND_PORT'); frontend_port="${frontend_port:-8430}"

# Which frontend is about to start. Read from the resolved config, not from
# COMPOSE_FILE in .env, because a shell override would otherwise make this
# report the wrong thing - and the two frontends look identical from the port.
# The `|| true` matters: with no frontend block, or none with a build target,
# grep exits non-zero and this script runs under `set -e`.
frontend_target=$(docker compose config --no-interpolate 2>/dev/null \
  | sed -n '/^  frontend:/,/^  [a-z][a-z_-]*:/p' | grep -m1 -oE 'target: [a-z]+' | cut -d' ' -f2 || true)
if [ "$frontend_target" = "production" ]; then
  frontend_mode="nginx image - a frontend change needs a rebuild"
else
  frontend_mode="Vite dev server - source bind-mounted, edits hot-reload"
fi

echo "=========================================="
echo "  OpenColab — Starting services"
echo "=========================================="
echo ""

docker compose up -d $BUILD_FLAG

echo ""
echo "Waiting for services to be ready..."

# Wait for backend health endpoint (up to 120s, backend loads ML models on startup)
backend_ok=0
for i in $(seq 1 24); do
  if curl -sf "http://localhost:${api_port}/api/v1/health" > /dev/null 2>&1; then
    backend_ok=1
    break
  fi
  sleep 5
done

echo ""
echo "=========================================="
echo "  OpenColab"
echo "=========================================="
echo ""
echo "  Frontend:  http://localhost:${frontend_port}  (${frontend_mode})"
echo "  Backend:   http://localhost:${api_port}  $([ "$backend_ok" = 1 ] && echo '(ready)' || echo '(not answering yet)')"
echo ""
if [ "$backend_ok" != 1 ]; then
  # A container that exited is not the same problem as a slow one: seeding the
  # admin user or migrating the database both abort the process.
  if [ -n "$(docker compose ps -q --status=exited 2>/dev/null)" ]; then
    echo "  These containers have exited - this is a configuration error, not a slow start:"
    docker compose ps --status=exited
    echo "  Read it with: docker compose logs api"
    echo ""
  else
    echo "  Still starting. The first start downloads embedding models and may"
    echo "  take 1-2 minutes: docker compose logs -f api"
    echo ""
  fi
fi
echo "  Login: admin, with the password from OPENCOLAB_ADMIN_PASSWORD in .env"
echo "  (no fixed default - the account is seeded from that variable on first run)."
echo ""
echo "  Logs:   docker compose logs -f api worker"
echo "  Stop:   ./scripts/docker-stop.sh"
echo ""
