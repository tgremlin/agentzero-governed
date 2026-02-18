CREATE TABLE IF NOT EXISTS governance.actors (
  actor_id TEXT PRIMARY KEY,
  actor_type TEXT NOT NULL,
  display_name TEXT NOT NULL,
  auth_subject TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  disabled_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS governance.audit_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id TEXT NOT NULL UNIQUE,
  schema_version TEXT NOT NULL,
  taxonomy_version TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  deployment_id TEXT NOT NULL,
  environment TEXT NOT NULL,
  run_id TEXT NOT NULL,
  sequence_number BIGINT NOT NULL,
  event_type TEXT NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL,
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  trace_id TEXT,
  span_id TEXT,
  parent_span_id TEXT,
  actor_id TEXT NOT NULL REFERENCES governance.actors(actor_id),
  actor_type TEXT NOT NULL,
  subject_kind TEXT,
  subject_name TEXT,
  subject_version TEXT,
  contract_id TEXT,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  payload_hash TEXT NOT NULL,
  contains_secrets BOOLEAN NOT NULL DEFAULT FALSE,
  contains_pii BOOLEAN NOT NULL DEFAULT FALSE,
  redaction_ratio REAL NOT NULL DEFAULT 0.0,
  consent_scope TEXT NOT NULL DEFAULT 'audit_only',
  integrity_chain_id TEXT NOT NULL,
  prev_event_hash TEXT NOT NULL,
  event_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, run_id, sequence_number)
);

CREATE INDEX IF NOT EXISTS ix_governance_audit_events_run
  ON governance.audit_events(tenant_id, run_id, sequence_number);
CREATE INDEX IF NOT EXISTS ix_governance_audit_events_type_ts
  ON governance.audit_events(event_type, observed_at);
CREATE INDEX IF NOT EXISTS ix_governance_audit_events_event_id
  ON governance.audit_events(event_id);

CREATE TABLE IF NOT EXISTS governance.policy_decisions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  sequence_number BIGINT NOT NULL,
  policy_name TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  decision TEXT NOT NULL,
  reason_codes TEXT[] NOT NULL DEFAULT '{}',
  observed_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_governance_policy_decisions_run
  ON governance.policy_decisions(tenant_id, run_id, sequence_number);
