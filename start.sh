#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.client.yml}"

if [[ -z "${A0_DATA_DIR:-}" && -d "/opt/agentzero/data/usr" ]]; then
  export A0_DATA_DIR="/opt/agentzero/data"
fi
A0_DATA_DIR="${A0_DATA_DIR:-./client-data}"
export A0_DATA_DIR

mkdir -p "${A0_DATA_DIR}/usr" "${A0_DATA_DIR}/tmp" "${A0_DATA_DIR}/logs" "${A0_DATA_DIR}/knowledge"

echo "[start] using compose file: ${COMPOSE_FILE}"
echo "[start] using data dir: ${A0_DATA_DIR}"
echo "[start] starting client stack (app + postgres + temporal + worker)"
docker compose -f "${COMPOSE_FILE}" up -d --build

echo "[start] done. open: http://127.0.0.1:50001"
