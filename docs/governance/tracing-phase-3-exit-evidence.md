# Tracing Phase 3 Exit Evidence

## Scope
This document captures deterministic evidence that Phase 3 goals are complete:
- training trigger automation
- release gate promotion/canary/rollback behavior
- rollback drill proof
- scheduled ops-cycle artifacts

## Required evidence set
1. Preflight gate artifacts:
- `client-data/tmp/governance-preflight/eval-report.json`
- `client-data/tmp/governance-preflight/release-gate.json`

2. Ops cycle artifacts:
- `client-data/tmp/governance-ops/dataset.*.training.manifest.json`
- `client-data/tmp/governance-ops/trigger.*.json`
- `client-data/tmp/governance-ops/dashboard.*.json`

3. Rollback drill artifacts:
- `client-data/tmp/governance-phase3-drill/phase3-drill.eval-report.json`
- `client-data/tmp/governance-phase3-drill/phase3-drill.release-gate.json`
- `client-data/tmp/governance-phase3-drill/phase3-drill.summary.json`

## Commands
Run from `data/a0/`.

```bash
PROJECT_NAME=<project_slug> tools/governance_release_preflight.sh
docker compose -f docker-compose.client.yml exec -T app /opt/venv-a0/bin/python /a0/tools/governance_ops_cycle.py --project-name <project_slug> --datasets-dir /a0/tmp/governance-ops
docker compose -f docker-compose.client.yml exec -T app /opt/venv-a0/bin/python /a0/tools/governance_phase3_rollback_drill.py --output-dir /a0/tmp/governance-phase3-drill
```

## Pass criteria
- Preflight release decision is `promote` or `canary` (never `rollback` for healthy candidate).
- Rollback drill decision is exactly `rollback`.
- Audit schema check and trace health check pass in preflight.
- Ops-cycle writes manifests, trigger decision, retention report, and dashboard snapshot.
