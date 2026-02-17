from __future__ import annotations

import json
import os
import threading
import uuid
from typing import Any

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
