#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.client.yml}"
APP_IMAGE_NAME="${APP_IMAGE_NAME:-agentzero-governed}"
APP_IMAGE_TAG="${APP_IMAGE_NAME}:latest"
FORCE_REBUILD="${FORCE_REBUILD:-false}"
BUILD_TIMEOUT_SECONDS="${BUILD_TIMEOUT_SECONDS:-1800}"

if [[ -z "${A0_DATA_DIR:-}" && -d "/opt/agentzero/data/usr" ]]; then
  export A0_DATA_DIR="/opt/agentzero/data"
fi
A0_DATA_DIR="${A0_DATA_DIR:-./client-data}"
export A0_DATA_DIR

mkdir -p "${A0_DATA_DIR}/usr" "${A0_DATA_DIR}/tmp" "${A0_DATA_DIR}/logs" "${A0_DATA_DIR}/knowledge"
mkdir -p "./data/temporal/dynamicconfig"
if [[ ! -f "./data/temporal/dynamicconfig/development.yaml" ]]; then
  echo "{}" > "./data/temporal/dynamicconfig/development.yaml"
fi

echo "[start] using compose file: ${COMPOSE_FILE}"
echo "[start] using data dir: ${A0_DATA_DIR}"
echo "[start] using app image: ${APP_IMAGE_TAG}"

compose_build_app() {
  if command -v timeout >/dev/null 2>&1; then
    timeout "${BUILD_TIMEOUT_SECONDS}" docker compose -f "${COMPOSE_FILE}" build app
  else
    docker compose -f "${COMPOSE_FILE}" build app
  fi
}

if [[ "${FORCE_REBUILD,,}" == "true" ]]; then
  echo "[start] FORCE_REBUILD=true, rebuilding app image (timeout ${BUILD_TIMEOUT_SECONDS}s)"
  compose_build_app
elif ! docker image inspect "${APP_IMAGE_TAG}" >/dev/null 2>&1; then
  echo "[start] app image not found locally, building app image once (timeout ${BUILD_TIMEOUT_SECONDS}s)"
  compose_build_app
else
  echo "[start] app image exists locally, skipping rebuild"
fi

echo "[start] starting client stack (app + postgres + temporal + worker)"
docker compose -f "${COMPOSE_FILE}" up -d --no-build

echo "[start] done. open: http://127.0.0.1:50001"
