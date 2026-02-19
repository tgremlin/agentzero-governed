# Tracing Phase 3: Training And Evaluation Ops (3-4 Weeks)

## Goal
Operationalize small-model adaptation loop using governed datasets.

## Scope
- Training trigger service (volume, drift, quality thresholds)
- Eval harness (tool validity, policy adherence, outcome quality)
- Canary rollout + rollback gates
- Adapter/model registry metadata for per-task families

## Deliverables
- Automated training trigger job
- Evaluation suite and scoring reports
- Promotion policy for candidate adapters
- Rollback automation tied to runtime regressions

## Commit Plan
1. `feat(training): add trigger criteria service and schedules`
2. `feat(eval): add governed eval harness and benchmark suite`
3. `feat(release): add adapter promotion and rollback gates`
4. `feat(observability): add training lifecycle events and dashboards`
5. `test(training): add canary/rollback policy tests`

## PR Plan
- PR-1: Triggering + training metadata plumbing
- PR-2: Eval harness + baseline reports
- PR-3: Promotion/canary/rollback automation

## Exit Criteria
- Automated trigger emits candidate training jobs with audit trail
- Candidate adapters gated by deterministic eval thresholds
- Canary rollback proven in staging drill

## Validation Artifacts
- Exit evidence pack: `docs/governance/tracing-phase-3-exit-evidence.md`
- Manual review checklist: `docs/governance/tracing-phase-3-manual-review.md`
