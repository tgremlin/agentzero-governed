#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.e2e.yml"
COMPOSE=(docker compose -f "${COMPOSE_FILE}")

KEEP_STACK="${KEEP_STACK:-0}"

cleanup() {
  if [[ "${KEEP_STACK}" == "1" ]]; then
    echo "[e2e] KEEP_STACK=1, leaving stack running"
    return
  fi
  echo "[e2e] stopping stack"
  "${COMPOSE[@]}" down --remove-orphans --volumes
}

trap cleanup EXIT

echo "[e2e] building images"
"${COMPOSE[@]}" build e2e

echo "[e2e] running governance e2e pytest subset"
"${COMPOSE[@]}" run --rm e2e

echo "[e2e] all checks passed"
