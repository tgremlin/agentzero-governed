# Phase 3 Manual Review Checklist

## Goal
Manual verification steps before declaring Phase 3 complete for release readiness.

## 1) Governance preflight review
- Run: `PROJECT_NAME=<project_slug> tools/governance_release_preflight.sh`
- Confirm in `release-gate.json`:
  - `decision` is not `rollback`
  - `validation_errors` is empty
- Confirm in preflight health report:
  - `dataset_exports_present` is `ok`
  - `training_lifecycle_present` is `ok`
  - `active_run_count` is `ok`

## 2) Rollback path review
- Run rollback drill:
  - `docker compose -f docker-compose.client.yml exec -T app /opt/venv-a0/bin/python /a0/tools/governance_phase3_rollback_drill.py --output-dir /a0/tmp/governance-phase3-drill`
- Confirm `phase3-drill.summary.json`:
  - `ok: true`
  - `actual_decision: rollback`

## 3) Ops cycle review
- Run:
  - `docker compose -f docker-compose.client.yml exec -T app /opt/venv-a0/bin/python /a0/tools/governance_ops_cycle.py --project-name <project_slug> --datasets-dir /a0/tmp/governance-ops`
- Confirm new timestamped outputs exist:
  - `dataset.*.training.manifest.json`
  - `trigger.*.json`
  - `dashboard.*.json`
  - `retention.*.json`

## 4) CI workflow review
- Ensure these workflows are enabled and green:
  - `governance-trace-gates`
  - `governance-ops-cycle`
  - `governance-phase3-rollback-drill` (manual run)
  - `custom-regressions`

## 5) Sign-off
- Attach artifact links/screenshots to PR.
- Record date, operator, and commit SHA used for manual validation.
