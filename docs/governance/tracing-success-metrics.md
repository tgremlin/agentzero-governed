# Governed Tracing Success Metrics

## KPI Groups
## 1) Compliance And Audit
- `event_coverage_rate` >= 95%: governed runs with complete required event set.
- `actor_attribution_rate` = 100%: events with valid `actor_id` and `actor_type`.
- `secret_leak_persisted_count` = 0: persisted payloads flagged with unredacted secrets.
- `audit_query_sla_p95` <= 3s: p95 response for key audit queries.

## 2) Runtime Reliability
- `tool_contract_pass_rate` >= 98% on governed production runs.
- `policy_decision_capture_rate` = 100% for governed tool calls.
- `schema_validation_fail_rate` <= 1% (excluding synthetic tests).
- `mean_retry_count` trending down release-over-release.

## 3) Data Flywheel Quality
- `train_eligible_yield` >= 30% of completed governed runs.
- `gold_yield` >= 10% of completed governed runs.
- `lineage_completeness` = 100%: dataset rows contain source event IDs.
- `consent_filter_accuracy` = 100% in dataset export tests.

## 4) Model Improvement Readiness
- `json_tool_call_validity` improvement target: +10% over baseline.
- `policy_violation_rate` non-increasing after model updates.
- `approval_reject_rate` non-increasing on target task families.

## Operational Dashboards
- Audit integrity and attribution dashboard
- Tool contract and policy outcome dashboard
- Training yield funnel (runs -> eligible -> gold)
- Drift and retraining trigger dashboard

## Release Gates
- Block release if:
  - `secret_leak_persisted_count > 0`
  - `policy_decision_capture_rate < 100%`
  - `consent_filter_accuracy < 100%`
  - Critical audit query checks fail

