#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.client.yml}"
if [[ -z "${A0_DATA_DIR:-}" && -d "/opt/agentzero/data/usr" ]]; then
  export A0_DATA_DIR="/opt/agentzero/data"
fi
export A0_DATA_DIR="${A0_DATA_DIR:-./client-data}"

echo "[stop] stopping new stack"
docker compose -f "${COMPOSE_FILE}" down

echo "[stop] done"
