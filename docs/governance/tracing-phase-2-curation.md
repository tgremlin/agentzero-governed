# Tracing Phase 2: Data Curation And Dataset Pipeline (2-3 Weeks)

## Goal
Convert governed traces into reproducible, consent-aware training/eval datasets.

## Scope
- Consent enforcement in exports (`audit_only|eval_allowed|training_allowed`)
- Episode builder (`run_id` -> canonical JSONL rows)
- Deterministic quality scoring (`train_eligible`, `gold`)
- Dataset lineage metadata and version tags
- Candidate tracks for review queues:
  - `llm_training`
  - `agent_tooling`
  - `harness_improvement`

## Deliverables
- Export CLI/service for dataset generation
- Quality scorer module + thresholds
- Dataset manifest format and lineage tests
- Retention and deletion handling for training artifacts

## Commit Plan
1. `feat(dataset): add consent-aware export filters`
2. `feat(dataset): add episode builder for governed runs`
3. `feat(dataset): add quality scoring and labels`
4. `feat(dataset): add lineage metadata and version manifests`
5. `test(dataset): add consent and lineage regression tests`

## PR Plan
- PR-1: Consent and export filter layer
- PR-2: Episode builder + scorer
- PR-3: Lineage + versioning + tests

## Exit Criteria
- 100% consent filter accuracy in test suite
- Reproducible dataset build from same input window
- Training yield dashboard available (`runs -> eligible -> gold`)
- Candidate API supports track-separated filtering/ranking for review and export
