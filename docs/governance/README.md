# Governance Mode (MVP)

## What It Is

Governance mode is a project-scoped runtime enforcement layer for Agent Zero.
When governance is enabled for the active project, governed tools must pass the runtime gate before execution.

## Project Scope

- No active project: governance is OFF (default Agent Zero autonomy).
- Active project with `governance_enabled=false`: autonomy/prototype mode.
- Active project with `governance_enabled=true`: runtime gate is enforced.

## Enforcement Model

Runtime enforcement only. Prompt instructions do not bypass policy.

Primary gate paths:
- `agent.py` tool dispatcher gate before `tool.execute`.
- `input.py` nested `CodeExecution` path gated.
- `code_execution_tool.py` runtime provenance assertion.
- `tty_session.py` shell-spawn provenance assertion.

## Approval Flow

1. Gate evaluates tool call + risk.
2. If approval required: `approval.requested` is persisted and context is paused.
3. UI shows inline Approval Card in chat.
4. User clicks Approve/Reject (optional rationale).
5. Backend records `approval.resolved`, updates status, unpauses context.

Governance snapshot fields exposed to UI:
- `approvals[]`
- `governance_events[]`

## UI (Approval Cards)

Approval Cards are rendered inline in the chat stream.
Each card shows:
- Tool name
- Args/command/plan
- Risk level
- Optional rationale textbox
- Approve/Reject actions

Buttons call `POST /governance_approval` with:
- `context_id`
- `approval_id`
- `decision` (`approved` or `denied`)
- `rationale`

Card state updates on the next poll cycle from snapshot data.

## Security Posture

Goal: no bypass in governed mode.

Guardrails include:
- Central dispatcher gate
- Nested execution path gating
- Provenance token assertions at runtime
- Static sentinel checks in CI

## Known Limitations (MVP)

- Same-user approvals only.
- Postgres persistence is behind feature flags and optional dependency.
- Temporal orchestration integration is deferred.
- In offline dev environments, local pytest setup may fail due dependency fetch limits; CI remains verification source of truth.

## Persistence Flags

- `GOV_PERSIST_BACKEND=file|postgres` (default `file`)
- `GOV_DUAL_WRITE=true|false` (default `false`)
- `DATABASE_URL=postgresql+psycopg://...` (required when backend is `postgres`)
