#!/bin/bash
# Stop OpenColab Docker Compose services.
# Run from the opencolab/ directory: ./scripts/docker-stop.sh
#
# Options:
#   --volumes    Also remove persistent data volumes (postgres, qdrant, uploads)
#                WARNING: this permanently deletes all stored data.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VOLUMES_FLAG=""
for arg in "$@"; do
  case "$arg" in
    --volumes)
      VOLUMES_FLAG="--volumes"
      echo "Warning: --volumes flag will permanently delete all database and vector store data."
      read -rp "Are you sure? [y/N] " confirm
      if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "Aborted."
        exit 0
      fi
      ;;
    *)
      echo "Unknown option: $arg"
      echo "Usage: $0 [--volumes]"
      exit 1
      ;;
  esac
done

echo "Stopping OpenColab services..."
docker compose down $VOLUMES_FLAG

echo ""
if [ -n "$VOLUMES_FLAG" ]; then
  echo "Services stopped and volumes removed."
else
  echo "Services stopped. Data volumes are preserved."
  echo "To also remove volumes: $0 --volumes"
fi
echo ""
