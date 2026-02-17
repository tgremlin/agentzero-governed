#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.client.yml}"

echo "[start] using compose file: ${COMPOSE_FILE}"
echo "[start] starting client stack (app + postgres + temporal + worker)"
docker compose -f "${COMPOSE_FILE}" up -d --build

echo "[start] done. open: http://127.0.0.1:50001"
