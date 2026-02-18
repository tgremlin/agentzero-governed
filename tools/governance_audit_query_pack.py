#!/usr/bin/env python3
from __future__ import annotations

import json
import os

from python.governance_runtime.db import connection
from python.governance_runtime.repos import GovernancePostgresRepo


def _fail(msg: str) -> int:
    print(json.dumps({"ok": False, "error": msg}))
    return 1


def _seed_events(run_id: str) -> None:
    repo = GovernancePostgresRepo()
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
            "type": "tool.contract.validation",
            "run_id": run_id,
            "thread_id": run_id,
            "sequence_number": 2,
            "tool_name": "github.create_pr",
            "contract_id": "gh.create_pr.v3",
            "passed": False,
            "actor_id": "actor_agent_runtime",
            "actor_type": "agent",
        }
    )
    repo.append_event(
        {
            "type": "approval.requested",
            "run_id": run_id,
            "thread_id": run_id,
            "sequence_number": 3,
            "actor_id": "actor_policy_engine",
            "actor_type": "policy",
        }
    )
    repo.append_event(
        {
            "type": "approval.resolved",
            "run_id": run_id,
            "thread_id": run_id,
            "sequence_number": 4,
            "decision": "approved",
            "actor_id": "actor_human_operator",
            "actor_type": "human_user",
        }
    )
    repo.append_event(
        {
            "type": "run.outcome",
            "run_id": run_id,
            "thread_id": run_id,
            "sequence_number": 5,
            "outcome": "success",
            "labels": {"tier": "gold"},
            "actor_id": "actor_agent_runtime",
            "actor_type": "agent",
        }
    )


def main() -> int:
    if str(os.environ.get("GOV_PERSIST_BACKEND", "")).strip().lower() != "postgres":
        return _fail("GOV_PERSIST_BACKEND must be postgres")

    run_id = "22222222-2222-2222-2222-222222222222"
    _seed_events(run_id)

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM (
                  SELECT
                    run_id,
                    MIN(observed_at) FILTER (WHERE event_type='approval.requested') AS requested_at,
                    MIN(observed_at) FILTER (WHERE event_type='approval.resolved') AS resolved_at
                  FROM governance.audit_events
                  WHERE tenant_id='tenant_default'
                  GROUP BY run_id
                ) x
                WHERE requested_at IS NOT NULL
                  AND resolved_at IS NOT NULL
                  AND resolved_at >= requested_at
                """
            )
            approval_latency_rows = int(cur.fetchone()[0] or 0)

            cur.execute(
                """
                SELECT COUNT(*)
                FROM governance.audit_events
                WHERE event_type = 'tool.contract.validation'
                  AND COALESCE(payload_json->>'passed', 'true') = 'false'
                """
            )
            contract_violations = int(cur.fetchone()[0] or 0)

            cur.execute(
                """
                SELECT
                  COUNT(*) FILTER (WHERE event_type='run.outcome') AS runs,
                  COUNT(*) FILTER (
                    WHERE event_type='run.outcome'
                      AND COALESCE(payload_json->'labels'->>'tier', '') IN ('tier2', 'gold')
                  ) AS train_eligible,
                  COUNT(*) FILTER (
                    WHERE event_type='run.outcome'
                      AND COALESCE(payload_json->'labels'->>'tier', '') = 'gold'
                  ) AS gold
                FROM governance.audit_events
                """
            )
            runs, train_eligible, gold = cur.fetchone()
            runs = int(runs or 0)
            train_eligible = int(train_eligible or 0)
            gold = int(gold or 0)

    ok = approval_latency_rows >= 1 and contract_violations >= 1 and runs >= 1 and train_eligible >= 1 and gold >= 1
    print(
        json.dumps(
            {
                "ok": ok,
                "run_id": run_id,
                "approval_latency_rows": approval_latency_rows,
                "contract_violations": contract_violations,
                "runs": runs,
                "train_eligible": train_eligible,
                "gold": gold,
            }
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
