CREATE SCHEMA IF NOT EXISTS governance;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS governance.runs (
  id UUID PRIMARY KEY,
  context_id TEXT NOT NULL,
  project_name TEXT,
  status TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_governance_runs_project_name ON governance.runs(project_name);
CREATE INDEX IF NOT EXISTS ix_governance_runs_status ON governance.runs(status);

CREATE TABLE IF NOT EXISTS governance.events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID,
  thread_id UUID,
  event_type TEXT NOT NULL,
  sequence_number BIGINT,
  event_ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_governance_events_event_ts ON governance.events(event_ts);
CREATE INDEX IF NOT EXISTS ix_governance_events_event_type ON governance.events(event_type);

CREATE TABLE IF NOT EXISTS governance.approvals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  approval_id TEXT NOT NULL UNIQUE,
  run_id UUID,
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
  UNIQUE(project_name, tool_call_hash)
);

CREATE INDEX IF NOT EXISTS ix_governance_approvals_project_status
  ON governance.approvals(project_name, status);
