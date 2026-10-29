#!/bin/bash
# Stop local dev servers by killing processes whose PIDs are stored in logs/
# If PID file is missing, fall back to killing processes on ports 8000 and 5173.
# Run from opencolab/ directory.

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SKIP_DOCKER=0
for arg in "$@"; do
  case "$arg" in
    --skip-docker) SKIP_DOCKER=1 ;;
    *)
      echo "Unknown option: $arg"
      echo "Usage: $0 [--skip-docker]"
      exit 1
      ;;
  esac
done

# ── Detect docker compose (v2 "docker compose" vs v1 "docker-compose") ──
detect_docker_compose() {
  if docker compose version &>/dev/null; then
    echo "docker compose"
  elif command -v docker-compose >/dev/null 2>&1 && docker-compose version &>/dev/null; then
    echo "docker-compose"
  else
    echo ""
  fi
}

# ── Find PIDs on a port (cross-platform: lsof -> fuser -> ss) ──
find_port_pids() {
  local port="$1"
  local pids

  # macOS/BSD: lsof is built-in
  pids=$(lsof -ti ":$port" 2>/dev/null) && { printf '%s' "$pids"; return 0; }
  # Linux: fuser (from psmisc)
  pids=$(fuser "$port/tcp" 2>/dev/null | tr -d ' ') && [ -n "$pids" ] && { printf '%s' "$pids"; return 0; }
  # Linux: parse ss output
  if command -v ss >/dev/null 2>&1; then
    pids=$(ss -tlnp "sport = :$port" 2>/dev/null | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | sort -u)
    [ -n "$pids" ] && { printf '%s' "$pids"; return 0; }
  fi
  return 1
}

stop_if_pid_exists() {
  local name="$1"
  local pid_file="$2"
  local port="$3"
  if [ -f "$pid_file" ]; then
    local pid
    pid=$(cat "$pid_file")
    if kill -0 "$pid" 2>/dev/null; then
      echo "Stopping $name (PID $pid)..."
      kill "$pid" 2>/dev/null || true
      rm -f "$pid_file"
      return
    else
      echo "$name: stale PID $pid, removing PID file"
      rm -f "$pid_file"
    fi
  fi
  # Fallback: kill process on port (handles orphan processes)
  if [ -n "$port" ]; then
    local pids
    pids=$(find_port_pids "$port" 2>/dev/null) || true
    if [ -n "$pids" ]; then
      echo "Stopping $name (port $port in use, PIDs: $pids)..."
      for p in $pids; do kill "$p" 2>/dev/null || true; done
    else
      echo "$name: not running"
    fi
  else
    echo "$name: not running (no PID file)"
  fi
}

stop_if_pid_exists "backend" "backend/logs/backend.pid" "8000"
stop_if_pid_exists "worker" "backend/logs/worker.pid" "8001"
stop_if_pid_exists "frontend" "frontend/logs/frontend.pid" "5173"

# Stop Docker dependency services
if [ "$SKIP_DOCKER" = 0 ]; then
  DOCKER_COMPOSE=$(detect_docker_compose)
  if [ -n "$DOCKER_COMPOSE" ]; then
    DOCKER_DEPS=(postgres qdrant)
    running_deps=()
    for svc in "${DOCKER_DEPS[@]}"; do
      state=$($DOCKER_COMPOSE ps --format '{{.Service}} {{.State}}' 2>/dev/null | awk -v s="$svc" '$1==s{print $2}')
      if [ "$state" = "running" ]; then
        running_deps+=("$svc")
      fi
    done
    if [ "${#running_deps[@]}" -gt 0 ]; then
      echo "Stopping Docker services: ${running_deps[*]}..."
      $DOCKER_COMPOSE stop "${running_deps[@]}"
    fi
  fi
fi

echo "Done."
