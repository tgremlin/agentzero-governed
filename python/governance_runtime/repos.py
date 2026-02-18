from __future__ import annotations

import json
import os
import threading
import uuid
from typing import Any

from python.governance_runtime.audit_events import (
    DEFAULT_ACTOR_ID,
    DEFAULT_ACTOR_TYPE,
    DEFAULT_CONSENT_SCOPE,
    DEFAULT_DEPLOYMENT_ID,
    DEFAULT_ENVIRONMENT,
    DEFAULT_TENANT_ID,
    build_audit_event,
)
from python.governance_runtime.db import connection, is_postgres_available


_GOVERNANCE_DDL = """
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

CREATE INDEX IF NOT EXISTS ix_governance_audit_events_run ON governance.audit_events(tenant_id, run_id, sequence_number);
CREATE INDEX IF NOT EXISTS ix_governance_audit_events_type_ts ON governance.audit_events(event_type, observed_at);
CREATE INDEX IF NOT EXISTS ix_governance_audit_events_event_id ON governance.audit_events(event_id);

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

CREATE INDEX IF NOT EXISTS ix_governance_policy_decisions_run ON governance.policy_decisions(tenant_id, run_id, sequence_number);
"""


def _env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def get_persist_backend() -> str:
    value = str(os.environ.get("GOV_PERSIST_BACKEND", "file")).strip().lower()
    return value if value in {"file", "postgres"} else "file"


def is_postgres_backend_enabled() -> bool:
    return get_persist_backend() == "postgres" and is_postgres_available()


def is_dual_write_enabled() -> bool:
    return _env_flag("GOV_DUAL_WRITE", default=False)


def _resolve_audit_sequence_number(prev_seq: int, candidate_sequence: Any) -> int:
    """Return a monotonic sequence number for audit_events unique key."""
    try:
        explicit_seq = int(candidate_sequence) if candidate_sequence is not None else None
    except Exception:
        explicit_seq = None
    if explicit_seq is not None and explicit_seq > prev_seq:
        return explicit_seq
    return prev_seq + 1


def _build_policy_decision_record(
    *,
    event: dict[str, Any],
    audit_event: dict[str, Any],
) -> dict[str, Any] | None:
    if str(audit_event.get("event_type", "")).strip() != "policy.check.decision":
        return None

    decision = str(event.get("decision", "")).strip().lower()
    if decision not in {"allow", "deny", "require_approval", "transform", "redact", "route", "quarantine"}:
        return None

    reason_codes_raw = event.get("reason_codes")
    reason_codes: list[str] = []
    if isinstance(reason_codes_raw, list):
        reason_codes = [str(x).strip() for x in reason_codes_raw if str(x).strip()]

    policy_name = str(event.get("policy_name", "governance_gate")).strip() or "governance_gate"
    policy_version = str(event.get("policy_version", "v1")).strip() or "v1"

    return {
        "event_id": str(audit_event.get("event_id", "")),
        "tenant_id": str(audit_event.get("tenant_id", "")),
        "run_id": str(audit_event.get("run_id", "")),
        "sequence_number": int(audit_event.get("sequence_number", 0)),
        "policy_name": policy_name,
        "policy_version": policy_version,
        "decision": decision,
        "reason_codes": reason_codes,
        "observed_at": str(audit_event.get("observed_at", "")),
    }


class GovernancePostgresRepo:
    def __init__(self) -> None:
        self._ddl_lock = threading.Lock()
        self._ddl_ready = False

    def _ensure_schema(self) -> None:
        if self._ddl_ready:
            return
        with self._ddl_lock:
            if self._ddl_ready:
                return
            with connection(autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(_GOVERNANCE_DDL)
            self._ddl_ready = True

    def upsert_approval(self, payload: dict[str, Any]) -> None:
        self._ensure_schema()
        tool_args_json = json.dumps(payload.get("tool_args", {}), sort_keys=True, default=str)
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO governance.approvals (
                      approval_id, project_name, tool_name, tool_call_hash,
                      risk_level, status, rationale, tool_args_json
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                    ON CONFLICT (approval_id)
                    DO UPDATE SET
                      project_name = EXCLUDED.project_name,
                      tool_name = EXCLUDED.tool_name,
                      tool_call_hash = EXCLUDED.tool_call_hash,
                      risk_level = EXCLUDED.risk_level,
                      status = EXCLUDED.status,
                      rationale = EXCLUDED.rationale,
                      tool_args_json = EXCLUDED.tool_args_json,
                      updated_at = now()
                    """,
                    (
                        payload.get("approval_id"),
                        payload.get("project_name"),
                        payload.get("tool_name"),
                        payload.get("tool_call_hash"),
                        payload.get("risk"),
                        payload.get("status", "pending"),
                        payload.get("rationale", ""),
                        tool_args_json,
                    ),
                )
            conn.commit()

    def get_approval_status(self, approval_id: str) -> str:
        self._ensure_schema()
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status FROM governance.approvals WHERE approval_id = %s",
                    (approval_id,),
                )
                row = cur.fetchone()
        if not row:
            return "pending"
        return str(row[0] or "pending").lower().strip()

    def resolve_approval(self, approval_id: str, status: str, rationale: str) -> dict[str, Any] | None:
        self._ensure_schema()
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE governance.approvals
                    SET status = %s,
                        rationale = %s,
                        updated_at = now()
                    WHERE approval_id = %s
                    RETURNING approval_id, project_name, tool_name, risk_level, tool_call_hash
                    """,
                    (status, rationale, approval_id),
                )
                row = cur.fetchone()
            conn.commit()
        if not row:
            return None
        return {
            "approval_id": row[0],
            "project_name": row[1],
            "tool_name": row[2],
            "risk": row[3],
            "tool_call_hash": row[4],
        }

    def append_event(self, event: dict[str, Any]) -> None:
        self._ensure_schema()
        event_type = str(event.get("type", "governance.event"))
        payload_json = json.dumps(event, sort_keys=True, default=str)
        run_id = event.get("run_id")
        thread_id = event.get("thread_id")
        sequence_number = event.get("sequence_number")
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO governance.events (run_id, thread_id, sequence_number, event_type, payload_json)
                    VALUES (%s, %s, %s, %s, %s::jsonb)
                    """,
                    (run_id, thread_id, sequence_number, event_type, payload_json),
                )
                actor_id = str(event.get("actor_id") or os.environ.get("A0_ACTOR_ID", DEFAULT_ACTOR_ID))
                actor_type = str(event.get("actor_type") or os.environ.get("A0_ACTOR_TYPE", DEFAULT_ACTOR_TYPE))
                tenant_id = str(event.get("tenant_id") or os.environ.get("A0_TENANT_ID", DEFAULT_TENANT_ID))
                deployment_id = str(
                    event.get("deployment_id") or os.environ.get("A0_DEPLOYMENT_ID", DEFAULT_DEPLOYMENT_ID)
                )
                environment = str(event.get("environment") or os.environ.get("A0_ENVIRONMENT", DEFAULT_ENVIRONMENT))
                consent_scope = str(event.get("consent_scope") or DEFAULT_CONSENT_SCOPE)
                audit_run_id = str(run_id or event.get("thread_id") or "governance-unscoped")

                cur.execute(
                    """
                    INSERT INTO governance.actors (actor_id, actor_type, display_name)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (actor_id) DO NOTHING
                    """,
                    (actor_id, actor_type, actor_id),
                )

                cur.execute(
                    """
                    SELECT sequence_number, event_hash
                    FROM governance.audit_events
                    WHERE tenant_id = %s AND run_id = %s
                    ORDER BY sequence_number DESC
                    LIMIT 1
                    """,
                    (tenant_id, audit_run_id),
                )
                prev = cur.fetchone()
                prev_seq = int(prev[0]) if prev else 0
                prev_hash = str(prev[1]) if prev else "sha256:0"

                audit_seq = _resolve_audit_sequence_number(prev_seq=prev_seq, candidate_sequence=sequence_number)

                audit_event = build_audit_event(
                    base_event=event,
                    tenant_id=tenant_id,
                    deployment_id=deployment_id,
                    environment=environment,
                    actor_id=actor_id,
                    actor_type=actor_type,
                    consent_scope=consent_scope,
                    run_id=audit_run_id,
                    sequence_number=audit_seq,
                    prev_event_hash=prev_hash,
                    trace_id=str(event.get("trace_id") or "") or None,
                    span_id=str(event.get("span_id") or "") or None,
                    parent_span_id=str(event.get("parent_span_id") or "") or None,
                )

                cur.execute(
                    """
                    INSERT INTO governance.audit_events (
                      event_id, schema_version, taxonomy_version, tenant_id, deployment_id, environment,
                      run_id, sequence_number, event_type, observed_at, recorded_at,
                      trace_id, span_id, parent_span_id,
                      actor_id, actor_type, subject_kind, subject_name, subject_version, contract_id,
                      payload_json, payload_hash, contains_secrets, contains_pii, redaction_ratio,
                      consent_scope, integrity_chain_id, prev_event_hash, event_hash
                    ) VALUES (
                      %s,%s,%s,%s,%s,%s,
                      %s,%s,%s,%s::timestamptz,%s::timestamptz,
                      %s,%s,%s,
                      %s,%s,%s,%s,%s,%s,
                      %s::jsonb,%s,%s,%s,%s,
                      %s,%s,%s,%s
                    )
                    """,
                    (
                        audit_event["event_id"],
                        audit_event["schema_version"],
                        audit_event["taxonomy_version"],
                        audit_event["tenant_id"],
                        audit_event["deployment_id"],
                        audit_event["environment"],
                        audit_event["run_id"],
                        audit_event["sequence_number"],
                        audit_event["event_type"],
                        audit_event["observed_at"],
                        audit_event["recorded_at"],
                        audit_event["trace_id"],
                        audit_event["span_id"],
                        audit_event["parent_span_id"],
                        audit_event["actor_id"],
                        audit_event["actor_type"],
                        audit_event["subject_kind"],
                        audit_event["subject_name"],
                        audit_event["subject_version"],
                        audit_event["contract_id"],
                        json.dumps(audit_event["payload_json"], sort_keys=True, default=str),
                        audit_event["payload_hash"],
                        bool(audit_event["contains_secrets"]),
                        bool(audit_event["contains_pii"]),
                        float(audit_event["redaction_ratio"]),
                        audit_event["consent_scope"],
                        audit_event["integrity_chain_id"],
                        audit_event["prev_event_hash"],
                        audit_event["event_hash"],
                    ),
                )

                policy_record = _build_policy_decision_record(event=event, audit_event=audit_event)
                if policy_record is not None:
                    cur.execute(
                        """
                        INSERT INTO governance.policy_decisions (
                          event_id, tenant_id, run_id, sequence_number,
                          policy_name, policy_version, decision, reason_codes, observed_at
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::timestamptz)
                        """,
                        (
                            policy_record["event_id"],
                            policy_record["tenant_id"],
                            policy_record["run_id"],
                            policy_record["sequence_number"],
                            policy_record["policy_name"],
                            policy_record["policy_version"],
                            policy_record["decision"],
                            policy_record["reason_codes"],
                            policy_record["observed_at"],
                        ),
                    )
            conn.commit()

    def create_run(self, context_id: str, project_name: str | None = None, status: str = "queued") -> str:
        self._ensure_schema()
        run_id = str(uuid.uuid4())
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO governance.runs (id, context_id, project_name, status)
                    VALUES (%s::uuid, %s, %s, %s)
                    """,
                    (run_id, context_id, project_name, status),
                )
            conn.commit()
        return run_id

    def ensure_run(
        self,
        *,
        run_id: str,
        context_id: str,
        project_name: str | None = None,
        status: str = "queued",
    ) -> None:
        self._ensure_schema()
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO governance.runs (id, context_id, project_name, status)
                    VALUES (%s::uuid, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (run_id, context_id, project_name, status),
                )
            conn.commit()

    def update_run_status(self, run_id: str, status: str) -> None:
        self._ensure_schema()
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE governance.runs
                    SET status = %s, updated_at = now()
                    WHERE id = %s::uuid
                    """,
                    (status, run_id),
                )
            conn.commit()

    def load_approvals(self, project_name: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        self._ensure_schema()
        limit_value = max(0, int(limit))
        query = (
            "SELECT approval_id, project_name, tool_name, tool_call_hash, risk_level, status, rationale, "
            "tool_args_json::text, created_at, updated_at "
            "FROM governance.approvals "
        )
        params: list[Any] = []
        if project_name:
            query += "WHERE project_name = %s "
            params.append(project_name)
        query += "ORDER BY updated_at DESC LIMIT %s"
        params.append(limit_value)

        items: list[dict[str, Any]] = []
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()
        for row in rows:
            try:
                tool_args = json.loads(row[7]) if row[7] else {}
            except Exception:
                tool_args = {}
            items.append(
                {
                    "approval_id": row[0],
                    "project_name": row[1],
                    "tool_name": row[2],
                    "tool_call_hash": row[3],
                    "risk": row[4],
                    "status": row[5],
                    "rationale": row[6] or "",
                    "tool_args": tool_args,
                    "created_at": row[8].isoformat() if row[8] else "",
                    "updated_at": row[9].isoformat() if row[9] else "",
                }
            )
        return items

    def load_events(self, project_name: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        self._ensure_schema()
        limit_value = max(0, int(limit))
        query = (
            "SELECT payload_json::text FROM governance.events "
            "ORDER BY event_ts DESC LIMIT %s"
        )
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (limit_value,))
                rows = cur.fetchall()

        events: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row[0]) if row and row[0] else {}
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                continue
            if project_name and str(payload.get("project_name", "")).strip() != str(project_name).strip():
                continue
            events.append(payload)
        return events


_repo_singleton: GovernancePostgresRepo | None = None
_repo_lock = threading.Lock()


def get_postgres_repo() -> GovernancePostgresRepo | None:
    global _repo_singleton
    if not is_postgres_backend_enabled():
        return None
    if _repo_singleton is not None:
        return _repo_singleton
    with _repo_lock:
        if _repo_singleton is None:
            _repo_singleton = GovernancePostgresRepo()
    return _repo_singleton
