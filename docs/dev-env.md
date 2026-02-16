# Dev Environment for Governance Work

## Python Environment

Agent Zero runs Python inside its configured runtime environment:
- Docker runtime: `/opt/venv-a0` (see `docker/run/fs/ins/setup_venv.sh`).
- Local host runtime: `python3` from your shell.

For local governance checks, use the helper script:

```bash
bash tools/setup_governance_test_env.sh
source .venv-governance/bin/activate
python3 tools/governance_sentinel.py
PYTHONPATH=. pytest -q tests/test_governance_input.py tests/test_snapshot_schema_v1.py
```

## Offline/Restricted Networks

If package installation fails (for example DNS or outbound access restrictions), pytest setup will fail locally.
In that case, use CI as the source of truth for the pytest subset and run only the sentinel locally if possible.

## CI Verification

The governance workflow installs test dependencies from `requirements.dev.txt`, then runs:
- `python3 tools/governance_sentinel.py`
- `PYTHONPATH=. pytest -q tests/test_governance_input.py tests/test_snapshot_schema_v1.py`
