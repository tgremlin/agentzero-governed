#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "[start] ensuring legacy container 'agentzero' is not running"
if docker ps -a --format '{{.Names}}' | grep -qx 'agentzero'; then
  docker stop agentzero >/dev/null 2>&1 || true
  docker rm agentzero >/dev/null 2>&1 || true
fi

echo "[start] starting new stack (app + postgres)"
docker compose -f docker-compose.e2e.yml up -d app postgres

echo "[start] done. open: http://127.0.0.1:50001"
