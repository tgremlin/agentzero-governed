# Control Plane Adapter

This integration enables AgentZero to use the Agent Control Plane (`/v1`) as the governance source of truth.

## Enable Adapter

Set:

- `CP_ADAPTER_ENABLED=true`
- `CP_API_URL=http://localhost:8080`
- `CP_DEPLOYMENT_ID=dep-local`
- `CP_TENANT_ID=<tenant-id>`
- `CP_RUNNER_TOKEN=<runner-token>`

Optional defaults:

- `CP_PROJECT_ID=<project-id>`
- `CP_EXECUTION_PROFILE=standard` (`regulated` supported later in runtime canary)
- `CP_INGESTOR_TOKEN=<events-token>` (recommended separate token)
- `CP_ADAPTER_STRICT_MODE=true` (requires separate ingestor token)
- `CP_RUN_TAG_PREFIX=agentzero` (prefix used for correlation tags, e.g. `agentzero:<context_id>`)
- `CP_CANARY_CORRELATION_TAG=canary:<id>` (optional explicit canary tag)

LLM gateway (feature-flagged):

- `CP_LLM_GATEWAY_URL=http://localhost:8091`
- `CP_LLM_GATEWAY_TOKEN=<gateway-token>`

Tool gateway placeholder:

- `CP_TOOL_GATEWAY_URL=<url>`

Approval polling tuning:

- `CP_APPROVAL_POLL_INITIAL_SECONDS=1.0`
- `CP_APPROVAL_POLL_MAX_SECONDS=5.0`
- `CP_APPROVAL_POLL_TIMEOUT_SECONDS=300`

## Runtime Behavior

When `CP_ADAPTER_ENABLED=true`:

- Agent starts/attaches a control-plane run via `POST /v1/runs`.
- Tool decisions route through `POST /v1/runtime/tool-decisions`.
- Approval holds use `context.paused` and poll `GET /v1/approvals/{approval_id}`.
- Canonical runtime events are ingested via `POST /v1/events:ingest`.
- Tool execution idempotency is guarded by per-run tool-call hash.
- Adapter emits `run.correlation` immediately after run creation with `cp_run_id`, `context_id`, adapter version, and correlation tags.

When disabled, AgentZero continues using existing local governance flow.

## Token Scope Guidance

Runner token (minimum):

- `runs:write`
- `policies:write`
- `runs:read`

Ingestor token (recommended separate):

- `events:ingest`

Strict mode:

- Enable `CP_ADAPTER_STRICT_MODE=true` to fail fast on unsafe settings.
- Strict mode requires distinct `CP_RUNNER_TOKEN` and `CP_INGESTOR_TOKEN`.
- Non-strict mode allows token fallback for local/dev and logs a warning.

Approvals are expected to be decided by operator/admin workflows, not by AgentZero runtime.

## Known Phase-1 Limits

- LLM gateway routing is optional and fallback-first.
- Full regulated egress/secret enforcement is deferred to `agent-runtime` Nomad canary phase.

## Verifier / Canary Correlation and Debugging

- Run tags are generated as: `agentzero`, `adapter:control-plane`, `<CP_RUN_TAG_PREFIX>:<context_id>` (or just prefix if no context), plus optional `CP_CANARY_CORRELATION_TAG`.
- To correlate verifier runs, filter control-plane runs by those tags, then match `run.correlation` event payload fields:
  - `cp_run_id`
  - `correlation.context_id`
  - `correlation.thread_id`
  - `correlation_tags`
- When debugging approval paths, inspect event order:
  - `tool.decision.requested` -> `policy.decision` -> `approval.waiting` -> `approval.resolved` -> (`tool.executed` or `tool.execution.denied`)
- `CP_EXECUTION_PROFILE=standard` is expected for local adapter/API canaries; regulated profile behavior depends on runtime/network controls added in `agent-runtime`.

## Trigger Response Contract

The canary trigger endpoint is implemented at `python/api/governance_run_start.py` and now returns both local and control-plane IDs.

Response fields:

- `agentzero_run_id` / `governance_run_id`: local Temporal/governance run identifier (also mirrored in `run_id` for compatibility).
- `cp_run_id`: canonical control-plane run ID.
  - required when `CP_ADAPTER_ENABLED=true` and adapter initialization succeeds.
  - `null` when adapter is disabled.
- `adapter_enabled`: whether CP adapter governance is active for this trigger.
- `execution_profile`: adapter execution profile (`standard` or `regulated`).
- `trigger_id`: per-trigger UUID.
- `started_at`: ISO-8601 timestamp.
- `correlation`: includes `tag`, `tags_applied`, `context_id`, `thread_id`, `source_framework`, `source_adapter`.

Failure behavior:

- If adapter is enabled but `cp_run_id` cannot be established, trigger returns a non-success JSON error (HTTP 502) with `cp_run_id_required=true`.
- Verifier/canary should prefer direct `cp_run_id` from trigger response and use tag-based correlation only as fallback.
- `cp_required` defaults to strict (`true`) and should not be disabled for verifier/canary or regulated runs.
- `cp_required=false` is a dev/debug compatibility override only:
  - rejected in strict mode, regulated profile, or when a canary correlation tag is configured;
  - requires explicit `CP_ALLOW_TRIGGER_CP_BYPASS=true` in non-strict local/dev contexts;
  - emits a warning in the trigger response when used.
