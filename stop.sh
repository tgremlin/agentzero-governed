#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "[stop] stopping new stack"
docker compose -f docker-compose.e2e.yml down

echo "[stop] done"
