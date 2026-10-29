#!/bin/bash
# Check if frontend and backend dev servers are running (by reading PID files)
# Run from opencolab/ directory.

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

check_pid() {
  local name="$1"
  local pid_file="$2"
  if [ -f "$pid_file" ]; then
    local pid
    pid=$(cat "$pid_file")
    if kill -0 "$pid" 2>/dev/null; then
      echo "$name: running (PID $pid)"
    else
      echo "$name: not running (stale PID file: $pid)"
    fi
  else
    echo "$name: not running (no PID file)"
  fi
}

check_pid "backend" "backend/logs/backend.pid"
check_pid "worker" "backend/logs/worker.pid"
check_pid "frontend" "frontend/logs/frontend.pid"
