#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

git config core.hooksPath .githooks
chmod +x .githooks/pre-commit

echo "Installed git hooks path: $(git config --get core.hooksPath)"
echo "pre-commit hook is active."
