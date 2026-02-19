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
- In offline dev environments, local pytest setup may fail due dependency fetch limits; CI remains verification source of truth.

## Persistence Flags

- `GOV_PERSIST_BACKEND=file|postgres` (default `file`)
- `GOV_DUAL_WRITE=true|false` (default `false`)
- `DATABASE_URL=postgresql+psycopg://...` (required when backend is `postgres`)
- `GOV_TEMPORAL_ENABLED=true|false` (default `false`)
- `TEMPORAL_HOST=temporal:7233`
- `TEMPORAL_NAMESPACE=default`
- `TEMPORAL_TASK_QUEUE=agentzero-governance`

## Client Deployment (Temporal + Postgres)

Use the repo-native client stack to run governance with Temporal orchestration and Postgres persistence:

```bash
cp .env.client.example .env
./start.sh
python3 tools/smoke_client_stack.py
```

If UI access is from a non-localhost origin (for example another machine on your LAN), set `ALLOWED_ORIGINS` in `.env` and restart:

```bash
ALLOWED_ORIGINS=http://localhost:50001,http://127.0.0.1:50001,http://192.168.10.121:50001
./stop.sh && ./start.sh
```

Persistent data root:
- Configure `A0_DATA_DIR` in `.env` (default `./client-data`).
- If `/opt/agentzero/data` exists, `start.sh` auto-uses it for backwards compatibility.

Expected smoke result:
- `{"ok": true, ...}` from `tools/smoke_client_stack.py`
- Governance APIs return `temporal: true` and `persisted: true`

Stop stack:

```bash
./stop.sh
```

## Slack Socket Listener (Optional)

This fork can bridge inbound Slack events to Agent Zero chats through Socket Mode.

Required secrets (Settings -> Secrets):
- `SLACK_BOT_TOKEN` (`xoxb-...`)
- `SLACK_APP_TOKEN` (`xapp-...`, scope `connections:write`)

Required env (`.env`):
- `SLACK_SOCKET_ENABLED=true`

Optional env:
- `SLACK_SOCKET_MODE=dm|mentions|both` (default `both`)
- `SLACK_SOCKET_REPLY_IN_THREAD=true|false` (default `true`)
- `SLACK_CONTEXT_LIFETIME_HOURS=720`
- `SLACK_A0_API_URL=http://app:5000`
- `SLACK_PROJECT_NAME=<project_slug>` to route Slack chats into a specific project

Behavior:
- DM events map to one persistent Agent Zero chat per Slack user.
- Mention events map to one persistent Agent Zero chat per Slack thread.
- Context mapping is persisted at `usr/slack/socket_context_map.json`.

## Tracing And Training Docs

- PRD: `docs/governance/tracing-prd.md`
- Success metrics: `docs/governance/tracing-success-metrics.md`
- Phase 1 (foundation): `docs/governance/tracing-phase-1-foundation.md`
- Phase 2 (curation): `docs/governance/tracing-phase-2-curation.md`
- Phase 3 (training ops): `docs/governance/tracing-phase-3-training-ops.md`
- Operations runbook: `docs/governance/tracing-operations-runbook.md`

## Trace Health Check

Use deterministic trace health checks before release promotions:

```bash
python3 tools/governance_trace_healthcheck.py \
  --project-name <project_slug> \
  --require-artifacts \
  --max-dataset-age-hours 168 \
  --max-lifecycle-age-hours 168
```

Exit code:
- `0`: healthy
- `1`: one or more checks failed

Validate audit schema/taxonomy versions before promotion:

```bash
python3 tools/governance_audit_schema_check.py --project-name <project_slug> --require-events
```
