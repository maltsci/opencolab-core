#!/bin/bash
# Build Docker images for api, worker, and frontend.
# Run from the opencolab/ directory: ./scripts/docker-build.sh
#
# Options:
#   --no-cache                 Force a clean build (passes --no-cache to docker compose)
#   --api                      Build API server image only
#   --worker                   Build worker image only
#   --frontend                 Build frontend image only
#   --apt-proxy=<host:port>    Enable APT proxy for image build (default endpoint: host.docker.internal:8001)

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BUILD_ARGS=""
TARGETS=()
APT_PROXY_HOST_PORT="${APT_PROXY_HOST_PORT:-host.docker.internal:8001}"
USE_APT_PROXY=0

for arg in "$@"; do
  case "$arg" in
    --no-cache) BUILD_ARGS="--no-cache" ;;
    --api)      TARGETS+=("api") ;;
    --worker)   TARGETS+=("worker") ;;
    --frontend) TARGETS+=("frontend") ;;
    --apt-proxy=*)
      APT_PROXY_HOST_PORT="${arg#*=}"
      USE_APT_PROXY=1
      ;;
    *)
      echo "Unknown option: $arg"
      echo "Usage: $0 [--no-cache] [--api] [--worker] [--frontend] [--apt-proxy=<host:port>]"
      exit 1
      ;;
  esac
done

COMPOSE_CMD=(docker compose build)
if [ -n "$BUILD_ARGS" ]; then
  COMPOSE_CMD+=("$BUILD_ARGS")
fi

if [ "$USE_APT_PROXY" -eq 1 ]; then
  APT_PROXY_URL="http://${APT_PROXY_HOST_PORT}"
  COMPOSE_CMD+=(
    --build-arg "APT_HTTP_PROXY=${APT_PROXY_URL}"
    --build-arg "APT_HTTPS_PROXY=${APT_PROXY_URL}"
  )
fi

echo "=========================================="
echo "  OpenColab — Docker image build"
echo "=========================================="
echo ""

if [ ${#TARGETS[@]} -gt 0 ]; then
  echo "Building: ${TARGETS[*]}"
  "${COMPOSE_CMD[@]}" "${TARGETS[@]}"
else
  echo "Building: api, worker, frontend"
  "${COMPOSE_CMD[@]}" api worker frontend
fi

echo ""
echo "Build complete."
echo "Run ./scripts/docker-start.sh to start all services."
echo ""
