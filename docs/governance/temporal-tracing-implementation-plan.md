# Governance + Temporal + Tracing Implementation Plan (Agent Zero)

## Scope and constraints
- Keep runtime governance enforcement in Agent Zero (no prompt-only security).
- Keep governance project-scoped: no active project => governance OFF.
- Keep changes segregated where possible (new governance runtime modules).
- Use Postgres as system-of-record for run/thread/event/approval/trace artifacts.
- Temporal integration wraps Agent Zero runtime; do not embed Temporal into core monologue loop.

## 1) Postgres DDL + migration plan

### 1.1 Schema overview
Use a dedicated schema `governance` to isolate custom data:

```sql
CREATE SCHEMA IF NOT EXISTS governance;
```

### 1.2 Core runtime tables

```sql
CREATE TABLE IF NOT EXISTS governance.projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_name TEXT NOT NULL UNIQUE,
  governance_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  governance_mode TEXT NOT NULL DEFAULT 'standard',
  policy_config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS governance.policy_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_name TEXT NOT NULL,
  policy_hash TEXT NOT NULL,
  policy_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(project_name, policy_hash)
);

CREATE TABLE IF NOT EXISTS governance.runs (
  id UUID PRIMARY KEY,
  context_id TEXT NOT NULL,
  project_name TEXT,
  policy_snapshot_id UUID REFERENCES governance.policy_snapshots(id),
  status TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_governance_runs_project_name ON governance.runs(project_name);
CREATE INDEX IF NOT EXISTS ix_governance_runs_status ON governance.runs(status);

CREATE TABLE IF NOT EXISTS governance.threads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES governance.runs(id) ON DELETE CASCADE,
  context_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, context_id)
);

CREATE TABLE IF NOT EXISTS governance.events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES governance.runs(id) ON DELETE CASCADE,
  thread_id UUID REFERENCES governance.threads(id) ON DELETE SET NULL,
  event_type TEXT NOT NULL,
  sequence_number BIGINT NOT NULL,
  event_ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE(run_id, sequence_number)
);

CREATE INDEX IF NOT EXISTS ix_governance_events_run_id_event_ts
  ON governance.events(run_id, event_ts);
CREATE INDEX IF NOT EXISTS ix_governance_events_event_type
  ON governance.events(event_type);

CREATE TABLE IF NOT EXISTS governance.approvals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  approval_id TEXT NOT NULL UNIQUE,
  run_id UUID NOT NULL REFERENCES governance.runs(id) ON DELETE CASCADE,
  project_name TEXT,
  tool_name TEXT NOT NULL,
  tool_call_hash TEXT NOT NULL,
  risk_level TEXT NOT NULL,
  status TEXT NOT NULL,
  rationale TEXT,
  requester_user_id TEXT,
  decider_user_id TEXT,
  tool_args_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, tool_call_hash)
);

CREATE INDEX IF NOT EXISTS ix_governance_approvals_run_id_status
  ON governance.approvals(run_id, status);
```

### 1.3 Trace tables (training/audit quality)

```sql
CREATE TABLE IF NOT EXISTS governance.trace_spans (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  trace_id TEXT NOT NULL,
  run_id UUID NOT NULL REFERENCES governance.runs(id) ON DELETE CASCADE,
  parent_span_id UUID REFERENCES governance.trace_spans(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'internal',
  status TEXT NOT NULL DEFAULT 'unset',
  started_at TIMESTAMPTZ NOT NULL,
  ended_at TIMESTAMPTZ,
  attributes_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  gen_ai_system TEXT,
  gen_ai_request_model TEXT,
  gen_ai_response_model TEXT,
  gen_ai_usage_input_tokens INTEGER,
  gen_ai_usage_output_tokens INTEGER
);

CREATE INDEX IF NOT EXISTS ix_gov_trace_spans_trace_started
  ON governance.trace_spans(trace_id, started_at);
CREATE INDEX IF NOT EXISTS ix_gov_trace_spans_run_id ON governance.trace_spans(run_id);

CREATE TABLE IF NOT EXISTS governance.trace_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  trace_id TEXT NOT NULL,
  run_id UUID NOT NULL REFERENCES governance.runs(id) ON DELETE CASCADE,
  span_id UUID NOT NULL REFERENCES governance.trace_spans(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  event_ts TIMESTAMPTZ NOT NULL,
  attributes_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_gov_trace_events_trace_ts
  ON governance.trace_events(trace_id, event_ts);

CREATE TABLE IF NOT EXISTS governance.trace_scores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  trace_id TEXT NOT NULL,
  run_id UUID NOT NULL REFERENCES governance.runs(id) ON DELETE CASCADE,
  metric_name TEXT NOT NULL,
  value DOUBLE PRECISION NOT NULL,
  event_ts TIMESTAMPTZ NOT NULL,
  details_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_gov_trace_scores_trace_metric
  ON governance.trace_scores(trace_id, metric_name);
```

### 1.4 Migration phases
1. Migration A: create schema + tables + indexes (no runtime switch).
2. Migration B: dual-write mode from governance gate (file + DB).
3. Migration C: read-path switch for UI snapshot (`approvals`, `governance_events`) to DB first.
4. Migration D: optional backfill script from `/tmp/agentzero/governance/*.json*` into Postgres.
5. Migration E: disable file write with feature flag after 2 stable releases.

## 2) Docker Compose patch plan (Temporal + Postgres + worker)

### 2.1 Why Docker
Yes, Temporal requires additional service(s); docker compose is the cleanest reproducible path.

### 2.2 Compose additions (proposed)
Add services to `/opt/agentzero/docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: agentzero
      POSTGRES_USER: agentzero
      POSTGRES_PASSWORD: agentzero
    ports:
      - "5432:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U agentzero -d agentzero"]
      interval: 10s
      timeout: 5s
      retries: 10

  temporal:
    image: temporalio/server:1.26.2
    entrypoint: ["temporal"]
    command:
      [
        "server", "start-dev",
        "--ip", "0.0.0.0",
        "--port", "7233",
        "--db-filename", "/var/lib/temporal/temporal.db",
        "--namespace", "agentzero"
      ]
    ports:
      - "7233:7233"
    volumes:
      - temporal-data:/var/lib/temporal
    healthcheck:
      test: ["CMD-SHELL", "temporal operator cluster health --address 127.0.0.1:7233 >/dev/null 2>&1"]
      interval: 10s
      timeout: 5s
      retries: 12

  temporal-ui:
    image: temporalio/ui:2.34.0
    environment:
      TEMPORAL_ADDRESS: temporal:7233
      TEMPORAL_UI_PORT: 8080
    ports:
      - "8233:8080"
    depends_on:
      temporal:
        condition: service_healthy

  a0-governance-worker:
    image: agent0ai/agent-zero:latest
    command: ["python", "-m", "python.governance_runtime.temporal_worker"]
    environment:
      TEMPORAL_HOST: temporal:7233
      TEMPORAL_NAMESPACE: agentzero
      TEMPORAL_TASK_QUEUE: agentzero-governance
      DATABASE_URL: postgresql+psycopg://agentzero:agentzero@postgres:5432/agentzero
    volumes:
      - ./data/a0:/a0
      - ./data/usr:/a0/usr
    depends_on:
      temporal:
        condition: service_healthy
      postgres:
        condition: service_healthy
```

Add envs to existing `agentzero` service:

```yaml
environment:
  - BRANCH=main
  - DATABASE_URL=postgresql+psycopg://agentzero:agentzero@postgres:5432/agentzero
  - TEMPORAL_HOST=temporal:7233
  - TEMPORAL_NAMESPACE=agentzero
  - TEMPORAL_TASK_QUEUE=agentzero-governance
  - GOV_PERSIST_BACKEND=postgres
```

Volumes:

```yaml
volumes:
  postgres-data:
  temporal-data:
```

### 2.3 Optional helper script
Add `tools/temporal-dev.sh` to start Temporal via compose, mirroring Agent Foundry ergonomics.

## 3) File-by-file patch plan (segregated-first)

### 3.1 New segregated modules (primary logic)
- `python/governance_runtime/db.py`
  - SQLAlchemy engine/session factory from `DATABASE_URL`.
- `python/governance_runtime/models.py`
  - ORM models for runs/threads/events/approvals/policy_snapshots/trace*.
- `python/governance_runtime/repos.py`
  - Persistence methods (`create_run`, `append_event`, `upsert_approval`, `resolve_approval`, `write_span`, ...).
- `python/governance_runtime/temporal_client.py`
  - Lazy Temporal client singleton.
- `python/governance_runtime/temporal_worker.py`
  - Worker bootstrapping, task queue registration.
- `python/governance_runtime/workflows/governed_run.py`
  - Workflow wrapper around Agent Zero run tick/resume.
- `python/governance_runtime/activities/*.py`
  - Activities for status sync, approval wait, trace sync, run tick bridge.
- `python/governance_runtime/migrations/*`
  - Alembic/SQL migrations for governance schema.

### 3.2 Minimal core touchpoints (required)
- `python/helpers/governance_gate.py`
  - Keep gate decisions + provenance; replace file persistence with repo calls.
  - Keep deterministic tool-call hash and idempotency.
- `python/helpers/state_snapshot.py`
  - Read `approvals[]` and `governance_events[]` from Postgres repository.
- `python/api/governance_approval.py`
  - Resolve approval via repository; if Temporal-enabled, send workflow signal.
- `python/helpers/projects.py`
  - Ensure policy settings persist and attach policy snapshot at run start.
- `python/tools/code_execution_tool.py`
  - Keep provenance assertion and token propagation.
- `python/helpers/tty_session.py`
  - Keep runtime backstop assertion.
- `agent.py`
  - Keep single dispatch chokepoint gate (already present).

### 3.3 API additions
- `python/api/governance_run_start.py`
  - Starts Temporal workflow for governed run.
- `python/api/governance_run_signal.py`
  - pause/resume/cancel signal path.
- `python/api/governance_events.py`
  - paginated events query from Postgres.
- `python/api/traces.py`
  - list/detail spans/events/scores.

### 3.4 UI integration files
- `webui/js/messages.js`
  - existing inline approval card remains.
- `webui/components/projects/project-edit-governance.html`
  - keep governance toggles; later add backend source indicator (file/db/temporal).
- `webui/js/index.js` and polling path
  - consume `approvals`, `governance_events`, and trace summary from DB-backed snapshot APIs.

### 3.5 Test plan files
- `tests/test_governance_input.py`
  - keep existing bypass/provenance tests.
- Add:
  - `tests/test_governance_persistence_db.py`
  - `tests/test_governance_temporal_signals.py`
  - `tests/test_governance_policy_snapshot_immutability.py`
  - `tests/test_trace_sync_schema.py`
- Keep/update sentinel:
  - `tools/governance_sentinel.py` (still enforce dispatch + provenance guarantees).

### 3.6 Rollout toggles
- `GOV_PERSIST_BACKEND=file|postgres` (default `file` first, then flip to `postgres`).
- `GOV_TEMPORAL_ENABLED=true|false` (default false in first DB-only rollout).
- `GOV_DUAL_WRITE=true|false` (temporary migration safety).

### 3.7 Proposed delivery sequence
1. Compose + DB migrations + repository layer.
2. Gate dual-write + snapshot read switch.
3. Temporal wrapper worker + start/signal APIs.
4. Trace spans/events/scores ingestion.
5. UI trace list/detail and dataset candidate groundwork.

### 3.8 Risks and controls
- Risk: bypass regressions during refactor.
  - Control: keep sentinel + provenance assertions unchanged.
- Risk: policy drift mid-run.
  - Control: immutable `policy_snapshot_id` per run.
- Risk: duplicate approvals.
  - Control: unique `(run_id, tool_call_hash)` idempotency key.
- Risk: rollout breakage.
  - Control: feature flags + dual-write transition window.
