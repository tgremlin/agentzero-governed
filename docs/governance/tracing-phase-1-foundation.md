# Tracing Phase 1: Foundation (2 Weeks)

## Goal
Ship minimum viable compliant tracing with deterministic event contracts.

## Scope
- Event taxonomy and enums (`v1`)
- Postgres audit tables (`actors`, `audit_events`, `policy_decisions`)
- Event emission SDK (single shared module)
- Secrets redaction + fail-closed ingestion guard
- First 10 high-value events in governed runtime

## Deliverables
- DDL migrations and tests
- Event schema validation tests
- Basic audit queries and smoke checks

## Commit Plan
1. `feat(governance): add canonical event enums and schema contracts`
2. `feat(governance): add audit ledger DDL and migrations`
3. `feat(governance): add fail-closed redaction and secret scan gate`
4. `feat(governance): emit v1 governed runtime audit events`
5. `test(governance): add schema and audit coverage tests`

## PR Plan
- PR-1: Event contracts + DDL
- PR-2: Redaction/secrets fail-closed pipeline
- PR-3: Runtime instrumentation + tests

## Exit Criteria
- Complete actor attribution for governed events
- Zero persisted secret payloads
- Audit query pack passes in CI

