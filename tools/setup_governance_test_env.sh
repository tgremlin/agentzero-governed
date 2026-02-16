#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PATH="${ROOT}/.venv-governance"

python3 -m venv "${VENV_PATH}"
"${VENV_PATH}/bin/python" -m pip install --upgrade pip
"${VENV_PATH}/bin/pip" install -r "${ROOT}/requirements.dev.txt"

echo "Environment ready. Run:"
echo "  source ${VENV_PATH}/bin/activate"
echo "  python3 tools/governance_sentinel.py"
echo "  PYTHONPATH=. pytest -q tests/test_governance_input.py tests/test_snapshot_schema_v1.py"
