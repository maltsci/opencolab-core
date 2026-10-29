#!/bin/bash
# Docker entrypoint for the backend service.
# Runs Alembic migrations (creates/upgrades all tables) then starts uvicorn.
# Alembic is idempotent: re-running on an already-migrated database is safe.

set -euo pipefail

echo "Running database migrations..."
alembic upgrade heads
echo "Migrations complete."

if [ "${OPENCOLAB_DEV_RELOAD:-false}" = "true" ]; then
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
