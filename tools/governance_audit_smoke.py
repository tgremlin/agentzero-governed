#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys

from python.governance_runtime.db import connection
from python.governance_runtime.repos import GovernancePostgresRepo


def _fail(msg: str) -> int:
    print(json.dumps({"ok": False, "error": msg}))
    return 1


def main() -> int:
    if str(os.environ.get("GOV_PERSIST_BACKEND", "")).strip().lower() != "postgres":
        return _fail("GOV_PERSIST_BACKEND must be postgres")

    repo = GovernancePostgresRepo()
    run_id = "11111111-1111-1111-1111-111111111111"
    repo.append_event(
        {
            "type": "run.started",
            "run_id": run_id,
            "thread_id": run_id,
            "sequence_number": 1,
            "actor_id": "actor_agent_runtime",
            "actor_type": "agent",
        }
    )
    repo.append_event(
        {
            "type": "policy.check.decision",
            "run_id": run_id,
            "thread_id": run_id,
            "sequence_number": 2,
            "decision": "allow",
            "reason_codes": ["policy.allowed"],
            "actor_id": "actor_policy_engine",
            "actor_type": "policy",
        }
    )

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM governance.audit_events WHERE run_id = %s",
                (run_id,),
            )
            total_events = int(cur.fetchone()[0] or 0)

            cur.execute(
                """
                SELECT COUNT(*)
                FROM governance.audit_events
                WHERE run_id = %s AND (
                    actor_id IS NULL OR actor_id = '' OR actor_type IS NULL OR actor_type = ''
                )
                """,
                (run_id,),
            )
            missing_actor = int(cur.fetchone()[0] or 0)

            cur.execute(
                """
                SELECT COUNT(*)
                FROM governance.audit_events
                WHERE run_id = %s
                  AND contains_secrets = true
                  AND payload_json NOT IN ('{}'::jsonb, '{"suppressed": true}'::jsonb)
                """,
                (run_id,),
            )
            unsuppressed_secret_payloads = int(cur.fetchone()[0] or 0)

            cur.execute(
                """
                WITH ordered AS (
                  SELECT sequence_number, prev_event_hash,
                         LAG(event_hash) OVER (ORDER BY sequence_number) AS prev_expected
                  FROM governance.audit_events
                  WHERE tenant_id = 'tenant_default' AND run_id = %s
                )
                SELECT COUNT(*)
                FROM ordered
                WHERE sequence_number > 1 AND prev_event_hash <> prev_expected
                """,
                (run_id,),
            )
            chain_breaks = int(cur.fetchone()[0] or 0)

    ok = (
        total_events >= 2
        and missing_actor == 0
        and unsuppressed_secret_payloads == 0
        and chain_breaks == 0
    )
    print(
        json.dumps(
            {
                "ok": ok,
                "run_id": run_id,
                "total_events": total_events,
                "missing_actor": missing_actor,
                "unsuppressed_secret_payloads": unsuppressed_secret_payloads,
                "chain_breaks": chain_breaks,
            }
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
