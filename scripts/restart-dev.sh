#!/bin/bash
# Restart frontend, backend, and worker dev servers.
# Stops app processes, runs database migrations, then starts everything again.
# Docker dependency services (postgres, qdrant) are left running.
# Run from opencolab/ directory.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Restarting dev servers..."
echo ""

"$ROOT/scripts/stop-dev.sh" --skip-docker

echo ""

"$ROOT/scripts/start-dev.sh"
