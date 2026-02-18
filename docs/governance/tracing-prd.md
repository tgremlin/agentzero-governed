# Governed Tracing And Training PRD

## Objective
Build a governed-mode tracing and data pipeline that supports:
- Compliance-grade audit trail (`who changed what, when, why`)
- High-quality training/eval dataset generation from normal usage
- Reliable fine-tuning/adapters path for small local models (`<=14B`)

## Scope
In scope:
- Canonical event schema + taxonomy
- Postgres audit ledger (append-only + integrity chain)
- OTel instrumentation conventions for governed runtime and tools
- Data curation pipeline and training eligibility labeling

Out of scope (v1):
- Multi-tenant SaaS shared-RLS model
- Full automated model training orchestration
- Advanced policy simulation sandbox

## Requirements
1. Security and compliance
- Never persist raw secrets in any sink.
- Every decision/action is actor-attributed and timestamped.
- Tamper-evident event chain per run.

2. Runtime reliability
- Deterministic event taxonomy and schema validation.
- Governed policy decisions captured as first-class events.
- Tool contract results captured for every tool invocation.

3. Data flywheel
- Per-tenant consent scopes: `audit_only|eval_allowed|training_allowed`.
- Deterministic quality scoring (`train_eligible`, `gold`).
- Dataset lineage from dataset row back to event IDs.

## Primary Users
- Operator/compliance reviewer
- Platform engineer
- ML engineer (dataset + adapter training)

## Deliverables
- Event schema and enums
- Audit DDL and ingestion library
- Phase-based rollout docs and dashboards

## Risks
- Over-collection of sensitive data
- Schema drift across services
- Low-quality datasets from unfiltered traces

## Acceptance Criteria
- Can answer: who approved/changed/ran what, when, and why.
- Can build reproducible dataset versions with explicit consent filtering.
- Can compute and track training yield over time.

