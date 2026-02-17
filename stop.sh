#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.client.yml}"

echo "[stop] stopping new stack"
docker compose -f "${COMPOSE_FILE}" down

echo "[stop] done"
